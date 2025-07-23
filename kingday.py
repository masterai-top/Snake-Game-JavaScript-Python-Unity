#! -*- coding:utf-8 -*-
# Author:   qianyong
# Created:  2016.06.30 19.43

from freetime.util import log as ftlog
from poker.entity.dao import daobase

from cars.entity import const
from cars.entity import carsconf
from cars.entity.util import UtilFunc

import time


class KingDay(object):
    '''水果王每天'''

    # 本地保存的前30名排行, 按winchips从大到小排序, 每天重置
    # 每个元素的格式 {userId: 132, purl: "http://asdfsaf", name: "zhangsan", winChips: 1234}
    _dayRanks = []

    # dayRank对应的是哪天的日期
    _dateForDayRank = ''

    # 上一次检查redis排行榜的时间点
    _lastCheckedRanksAt = 0

    # 30分钟检查一次redis里的排行榜
    CHECK_REDIS_RANKS_PERIOD = 30 * 60

    @classmethod
    def initialize(cls):
        '''初始化, 一段时间后启动周期扫描timer'''

        UtilFunc.callLater(cls.CHECK_REDIS_RANKS_PERIOD, cls._loopCheckRedisRanksPeriod)

    @classmethod
    def addWinChip(cls, userId, deltaChip, now):
        '''玩家赢金币时, 更新排行榜, 返回玩家今天总计赢的金币数'''

        today = cls._todayDate(now)

        # 获取玩家的每日赢取金币, 并更新
        dayData = UtilFunc.getDayData(userId, today)
        dayData['winChipsForKing'] += deltaChip
        UtilFunc.setDayData(userId, dayData, today)
        userDayWinChips = dayData['winChipsForKing']

        # 比最后一名的今日赢取金币数还低, 不用更新到榜上
        dayRanks = cls._getLocalDayRanks(today)
        if len(dayRanks) >= cls._maxRanksCount() and dayRanks[-1]['winChips'] >= userDayWinChips:
            return

        # 更新远程redis里的排行榜数据, 负分保存在redis里
        daobase.executeRankCmd('ZADD', cls._dayKey(today), -userDayWinChips, userId)

        # 更新本地的排行榜变量
        cls._updateLocalDayRanks(userId, userDayWinChips, today)

        return userDayWinChips

    @classmethod
    def getTodayGameRanks(cls, now):
        '''获取当天的前20名排行'''

        today = cls._todayDate(now)
        ranks = cls._getLocalDayRanks(today)

        maxCount = carsconf.getKingConf().get('today', {}).get('game_count', 1)
        return ranks[:maxCount]

    @classmethod
    def getYesterdayRanks(cls, now, count=None):
        '''获取头一天的前20名. 直接从redis读取'''

        yesterday = cls._todayDate(now - const.ONE_DAY_SEC)

        if count is None:
            count = cls._maxRanksCount()

        dayRanks = []
        parts = daobase.executeRankCmd('ZRANGE', cls._dayKey(yesterday), 0, count - 1, 'WITHSCORES')
        if not parts:
            parts = []

        for i in xrange(len(parts) / 2):
            userId = int(parts[i * 2])
            winChips = -int(parts[i * 2 + 1])
            user = cls._buildUser(userId, winChips)
            dayRanks.append(user)

        return dayRanks

    @classmethod
    def getYesterdayTop(cls, now):
        '''获取头一天的头名, 如果没有, 则返回None。 直接从redis读取'''

        ranks = cls.getYesterdayRanks(now, 1)
        if len(ranks) > 0:
            return ranks[0]
        else:
            return None

    @classmethod
    def setExpireRemoteRank(cls, now):
        '''远程redis里的当日rank数据最长保留往后推延24小时'''

        today = cls._todayDate(now)
        daobase.executeRankCmd('EXPIRE', cls._dayKey(today), 24 * 3600)

    @classmethod
    def getUserTodayWinChips(cls, userId, now):
        '''从redis获取某个用户今天的winchips'''

        today = cls._todayDate(now)
        data = UtilFunc.getDayData(userId, today)
        return data['winChipsForKing']

    @classmethod
    def _buildUser(cls, userId, winChips):
        '''构建user数据'''

        name, purl = UtilFunc.getUserNameAndPurl(userId)
        return {
            "userId": userId,
            "winChips": winChips,
            "name": name,
            "purl": purl
        }

    @classmethod
    def _dayKey(cls, date):
        '''每天排行的key'''

        return 'kingrank:%s:%s' % (const.GAME_ID, date)

    @classmethod
    def _todayDate(cls, now=None):
        '''返回当天的日期'''

        if now is None:
            now = time.time()
        return time.strftime("%Y%m%d", time.localtime(now))

    @classmethod
    def _getLocalDayRanks(cls, today):
        '''
        获取本地保存的当日的dayRank值

        :param today: 今天的日期
        :return: dayRank
        '''

        # 日期不同的话, 从redis刷新数据
        if today != cls._dateForDayRank:
            del cls._dayRanks[:]

            count = cls._maxRanksCount()

            parts = daobase.executeRankCmd('ZRANGE', cls._dayKey(today), 0, count - 1, 'WITHSCORES')
            if not parts:
                parts = []

            for i in xrange(len(parts) / 2):
                userId = int(parts[i * 2])
                winChips = -int(parts[i * 2 + 1])
                user = cls._buildUser(userId, winChips)
                cls._dayRanks.append(user)

            cls._dateForDayRank = today

        return cls._dayRanks

    @classmethod
    def _updateLocalDayRanks(cls, userId, winChips, today):
        '''更新本地的dayrank变量'''

        count = cls._maxRanksCount()
        dayRanks = cls._getLocalDayRanks(today)

        # 更新用户的分数
        index = cls._findUserInDayRanks(userId, dayRanks)
        if index >= 0:
            dayRanks[index]['winChips'] = winChips
        else:
            if len(dayRanks) < count:
                dayRanks.append(cls._buildUser(userId, winChips))
            else:
                dayRanks[-1] = cls._buildUser(userId, winChips)

        # 按分数从大到小排序
        dayRanks.sort(cmp=lambda a, b: cmp(a['winChips'], b['winChips']), reverse=True)

    @classmethod
    def _findUserInDayRanks(cls, userId, dayRank):
        '''找到用户在dayrank中的索引, 找不到时返回-1'''

        for i in xrange(len(dayRank)):
            if dayRank[i]['userId'] == userId:
                return i

        return -1

    @classmethod
    def _maxRanksCount(cls):
        '''排行榜最大存储的数量'''

        dayConf = carsconf.getKingConf().get('today', {})
        return max(dayConf.get('game_count', 1), dayConf.get('bi_count', 1))

    @classmethod
    def _loopCheckRedisRanksPeriod(cls):

        now = int(time.time())

        # 排行榜里成员数量
        today = cls._todayDate(now)
        countInRedis = daobase.executeRankCmd('ZCOUNT', cls._dayKey(today), '-inf', '+inf')
        if not countInRedis:
            countInRedis = 0
        countInRedis = int(countInRedis)
        ftlog.info('_loopCheckRedisRanksPeriod king ranks total length', countInRedis)

        # 超出预配置长度时, 要做裁剪
        maxCount = cls._maxRanksCount()
        if countInRedis > maxCount * 2:
            daobase.executeRankCmd('ZREMRANGEBYRANK', cls._dayKey(today), maxCount, -1)

        # 跟上次check的时间做比较, 跨越一天时, 输出BI统计需要的日志
        if UtilFunc.isAcrossTwoDays(now, cls._lastCheckedRanksAt):
            biCount = carsconf.getKingConf().get('today', {}).get('bi_count', 1)
            yesterday = cls._todayDate(now - const.ONE_DAY_SEC)
            parts = daobase.executeRankCmd('ZRANGE', cls._dayKey(yesterday), 0, biCount, 'WITHSCORES')
            if not parts:
                parts = []

            # BI统计需要的日志
            ftlog.info('King.Ranks.Yesterday:', parts)

        # 配置过期时间, 最长保留一天
        cls.setExpireRemoteRank(now)

        cls._lastCheckedRanksAt = now

        # 一段时间后, 再次调度自己
        UtilFunc.callLater(cls.CHECK_REDIS_RANKS_PERIOD, cls._loopCheckRedisRanksPeriod)
