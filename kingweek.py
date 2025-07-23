#! -*- coding:utf-8 -*-
# Author:   qianyong
# Created:  2016.06.25 18.16

from freetime.util import log as ftlog
from poker.entity.dao import daobase

from cars.entity import const
from cars.entity import carsconf

import json
import time
from poker.util import strutil


class KingWeek(object):
    '''水果王最近7天'''

    # redis里的key
    _weekKey = 'king:%s:%s' % (const.GAME_ID, const.FAKE_TABLE_ID)

    # 最近7天的水果王用户列表
    # 列表里每个成员的数据格式{userId: 123, name: "hello", purl: "http://sadfsaf", date: "06-12", 'claimed': false, 'winChips': 123}
    _weekList = None

    @classmethod
    def getWeekData(cls):
        '''获取水果王7天榜'''

        if cls._weekList is None:
            cls._weekList = []
            count = carsconf.getKingConf().get('week', {}).get('day_count', 7)  # 默认7天的

            parts = daobase.executeMixCmd('LRANGE', cls._weekKey, 0, count - 1)
            if not parts:
                parts = []

            for part in parts:
                cls._weekList.append(json.loads(part))

        return cls._weekList

    @classmethod
    def getSpecificDayKing(cls, t):
        '''获取t代表的那一天的小丑王, 如果取不到, 则返回None'''

        day = time.strftime("%m-%d", time.localtime(t))
        weekData = cls.getWeekData()
        for user in weekData:
            if user['date'] == day:
                return user
        return None

    @classmethod
    def buildDataForClient(cls):
        '''构建返回给客户端的数据'''

        data = strutil.cloneData(cls.getWeekData())
        for d in data:
            del d['claimed']
            del d['winChips']
        return data

    @classmethod
    def getUserClaimStatus(cls, userId):
        '''获取某个用户的领奖状态'''

        rtn = {'canClaim': False}

        weekList = cls.getWeekData()
        for d in weekList:
            if d['userId'] == userId and not d['claimed']:
                rtn['date'] = d['date']
                rtn['canClaim'] = True
                break

        return rtn

    @classmethod
    def setUserClaimedStatus(cls, userId, claimed):
        '''设置用户领取状态'''

        weekList = cls.getWeekData()
        for i in xrange(len(weekList)):
            user = weekList[i]
            if user['userId'] == userId and not user['claimed']:
                user['claimed'] = claimed

                # debug模式多一步断言检查, 不会操作错用户
                if ftlog.is_debug():
                    data = daobase.executeMixCmd('LINDEX', cls._weekKey, i)
                    assert json.loads(data)['userId'] == userId

                daobase.executeMixCmd('LSET', cls._weekKey, i, json.dumps(user))
                break

    @classmethod
    def appendYesterdayKing(cls, user_):
        '''
        更新昨天的king。 开奖时发现过了跨了一天时, 会调用该方法.

        :param user: 数据取自头一天的kingday的头名用户数据,格式跟那边的一样 {userId: 123, purl: "", name: "", winChips: ""}
        '''

        user = strutil.cloneData(user_)
        maxCount = carsconf.getKingConf().get('week', {}).get('day_count', 7)  # 默认7天的

        # 头一天的日期, 置可领奖状态
        user['date'] = time.strftime("%m-%d", time.localtime(time.time() - 24 * 3600))

        # 这天的水果王已经存在周榜里了, 不再存
        localWeekList = cls.getWeekData()
        for user_ in localWeekList:
            if user_['date'] == user['date']:
                return

        user['claimed'] = False

        data = json.dumps(user)
        ftlog.info('save yesterday king', data)

        daobase.executeMixCmd('LPUSH', cls._weekKey, data)
        localWeekList = cls.getWeekData()
        localWeekList.insert(0, user)
        if len(localWeekList) > maxCount:
            del localWeekList[maxCount:]

        # redis里的数据是否长度超过限制, 超过了则裁剪
        length = daobase.executeMixCmd('LLEN', cls._weekKey)
        if length and int(length) > maxCount * 2:
            daobase.executeMixCmd('LTRIM', cls._weekKey, 0, maxCount - 1)
