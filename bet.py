#! -*- coding:utf-8 -*-
# Author:   qianyong
# Created:  2016.06.29 18.13

from freetime.entity.msg import MsgPack
from freetime.util import log as ftlog

from cars.entity import const
from cars.entity import carsconf
from cars.entity import carschip
from cars.entity import carsled
from cars.entity.util import UtilFunc
from cars.gameplays.kingweek import KingWeek
from cars.gameplays.kingday import KingDay
from cars.gameplays.lottery import Lottery
from cars.gameplays.pool import Pool
from cars.gametable.carssender import Sender

import math
import random
import time
import stackless
from poker.util import strutil


class BetSystem(object):
    '''押注整个系统'''

    BROADCAST_FRUIT_BETTING_INTERVAL = 2  # 广播水果总注的时间间隔, 秒

    # 测试
    # 下局当作跨天0点,结算水果王
    _debugAcrossDaysKing = False

    def __init__(self, table):
        self._table = table
        self._betStatus = const.STATE_INIT  # 状态机
        self._bettingUsers = {}  # 本局有押注的玩家。可能会出现已掉线了不在self._table.users里的情况
        self._lastRoundTime = 0  # 上局总计时长
        self._fruitBettingChips = []  # 本局水果总注实况
        self._lastBroadcastedFruitBettingChips = []  # 上一次广播过的水果总注实况
        self._openFruitIds = []  # 当前这局开出的水果
        self._openLuckType = ''  # luck类型
        self._top = None  # 当前这局押注赢得最多的玩家的信息(winchips, name, purl, vipLevel)
        self._triggeredPool = False  # 当前这局是否触发了彩池奖励
        self._nextLotteryAt = 0  # 下一局开奖lottery的时间
        self._firstRound = True  # 是否为进程启动后第一轮开奖
        self._dayTotalBetChips = 0  # 当天总下注
        self._dayTotalWinBetChips = 0  # 当天玩家总赢取的下注金额
        self._lastSealAt = 0  # 上一局封盘的时间
        self._issueNum = UtilFunc.getIssueNum() + 1  # 当前这局的局号,超过百万则重置
        if self._issueNum >= 900000:
            self._issueNum = 1
        self._poolPrizeList = [] #彩池中彩列表
        UtilFunc.setIssueNum(self._issueNum)
        UtilFunc.callLater(2, self._loopBetState)
        UtilFunc.callLater(2, self._broadCastFruitBetting)

    @property
    def bettingUsers(self):
        return self._bettingUsers

    @property
    def nextLotteryAt(self):
        return self._nextLotteryAt

    @property
    def issueNum(self):
        return self._issueNum

    def setTableReadyState(self):
        '''设置准备押注状态'''

        self._betStatus = const.STATE_READY_BET
        self._poolPrizeList = []

    def setTableSealState(self):
        '''倒计时封盘, 不再接受下注, 并做玩家金币结算, 设置状态为 封盘'''

        self._betStatus = const.STATE_SEAL

        # 进入封盘时,再广播一次总注,客户端才能收到最新的总注情况
        self.doBroadCastFruitBetting()

        # 封盘期间就做所有玩家金币结算, 避免大量db操作堵塞开奖时间
        now = int(time.time())

        # 跨天了后清除当日返奖的相关数值
        if UtilFunc.isAcrossTwoDays(now, self._lastSealAt):
            self._dayTotalBetChips = 0
            self._dayTotalWinBetChips = 0
        self._lastSealAt = now

        # 是否出发彩池
        self._triggeredPool, rewardTimes = Pool.triggerPoolChip(self._getRewardRate())
        self._triggeredPoolTotal = 0
        self._poolPrizeList = []
        ftlog.debug("_poolPrizeList___", self._poolPrizeList, self._triggeredPool, rewardTimes)
        if self._triggeredPool and rewardTimes > 0:
            oldPoolChip = Pool.getPoolChip()
            # 将彩池奖励加到玩家金币上
            sumBetChips = sum(self._fruitBettingChips)
            for userId, user in self._bettingUsers.iteritems():
                user.winPoolChip = int(sum(user.fruitBetChips) * rewardTimes * oldPoolChip / sumBetChips)
                user.uchip = carschip.dnChipUpdate(userId, const.EVENT_POOL_WIN_CHIP, user.winPoolChip, user.clientId, user, now)
                self._triggeredPoolTotal += user.winPoolChip
                name, purl = UtilFunc.getUserNameAndPurl(user.userId)
                self._poolPrizeList.append({'name': name, 'winPoolChip': user.winPoolChip, 'purl': purl, 'userId': user.userId})
            self._poolPrizeList.sort(key=lambda u: u['winPoolChip'], reverse=True)

            # 从彩池扣除玩家赢走的彩池奖励
            if self._triggeredPoolTotal > 0:
                Pool.incrPoolChipByDeltaPoolChip(-self._triggeredPoolTotal)
                # 更新彩池中奖名单
                Pool.appendPoolList(oldPoolChip, self._triggeredPoolTotal)

            UtilFunc.reportGameEvent(const.EVENT_GAME_POOLPRIZE, 1, 1, self._table.roomId, self._table.tableId,
                                     tableChip=oldPoolChip, userChip=self._triggeredPoolTotal)
            self._openFruitIds, self._openLuckType = [const.CRAZE_ID], ""
        else:
            # 确定开奖的水果
            self._openFruitIds, self._openLuckType = self._openLottery()
        ftlog.debug("_poolPrizeList___", self._openFruitIds, self._openLuckType)

        # 水果倍数配置
        fruitsTimesConf = carsconf.getConf().get('pos_win_rates', [])
        for userId, user in self._bettingUsers.iteritems():
            user.winBetChip = self._calcUserWinChip(user, self._openFruitIds, fruitsTimesConf)
            self._dayTotalBetChips += user.betChip
            self._dayTotalWinBetChips += user.winBetChip

        ftlog.info('_openLottery ',
                   'dayTotalBetChips=', self._dayTotalBetChips,
                   'dayTotalWinBetChips=', self._dayTotalWinBetChips)

        # 查找本局押注赢得最多的玩家 => self._top
        maxWinChipUser = None
        for userId, user in self._bettingUsers.iteritems():
            if maxWinChipUser is None or maxWinChipUser.winBetChip < user.winBetChip:
                maxWinChipUser = user
        self._top = None
        if maxWinChipUser is not None and maxWinChipUser.winBetChip > 0:
            name, purl = UtilFunc.getUserNameAndPurl(maxWinChipUser.userId)
            self._top = {
                "userId": maxWinChipUser.userId,
                "winChips": maxWinChipUser.winBetChip,
                "name": name,
                "purl": purl,
                "vipLevel": UtilFunc.getUserVipLevel(maxWinChipUser.userId)
            }

        # 如果玩家押赢了,将本局的奖励添加到玩家金币上, 更新赢取记录
        for userId, user in self._bettingUsers.iteritems():
            if user.winBetChip > 0:
                user.uchip = carschip.dnChipUpdate(userId, const.EVENT_LOTTERY_WIN_CHIP, user.winBetChip, user.clientId, user, now)
                user.updateWinHistory(self._issueNum, user.winBetChip)

    def setTableLotteryState(self):
        '''设置状态为 开奖'''

        now = int(time.time())

        self._betStatus = const.STATE_LOTTERY

        # 新的一局要开出的水果, 时长, 和下局开奖时间点
        self._lastRoundTime = self._calcOneRoundTimeval(len(self._openFruitIds))
        self._nextLotteryAt = int(now + self._lastRoundTime + 0.5)  # +0.5为了四舍五入

        # 广播开奖结果

        # 跟上一轮的开奖时间相比,是否跨了凌晨0点, 做一些处理:决定是否要带上7天水果王数据
        isAcrossDay = UtilFunc.isAcrossTwoDays(now, now - self._lastRoundTime)
        if BetSystem._debugAcrossDaysKing:
            isAcrossDay = True

        # 跨天了需要更新水果王周数据, 并返回新的水果王周数据给用户
        weekKingList = None
        if isAcrossDay or self._firstRound:
            yesterdayTopUser = KingDay.getYesterdayTop(now)

            # 调试状态设置跨天的话,则用今天的去结算
            if BetSystem._debugAcrossDaysKing:
                yesterdayTopUser = None
                yesterdayUsers = KingDay.getTodayGameRanks(now)
                if len(yesterdayUsers) > 0:
                    yesterdayTopUser = yesterdayUsers[0]

            if yesterdayTopUser is not None:
                KingWeek.appendYesterdayKing(yesterdayTopUser)
            weekKingList = KingWeek.buildDataForClient()

            self._firstRound = False

        # 数字7, 西瓜的上次开奖距离现在的时间
        fruitsOpenTimeLeft = Lottery.getFruitLastOpenTimeLeft(now)

        maxWinChipUserId = 0  # 赢钱最多的玩家ID (winBetChip + winPoolChip)
        maxWinChip = 0  # 最多的赢钱 (winBetChip + winPoolChip)
        maxWinPoolList = self._poolPrizeList[:3]
        ftlog.debug("maxWinPoolList___", maxWinPoolList, self._triggeredPoolTotal)
        # 遍历在线玩家
        for userId, user in self._table.users.iteritems():
            # 如果跨天了, 同时也发送自己的水果王领奖状态
            myKingRewardStatus = None
            if isAcrossDay:
                myKingRewardStatus = KingWeek.getUserClaimStatus(userId)

            if userId in self._bettingUsers:  # 在线玩家且是押注用户
                Sender.sendLotteryMsg(userId,
                                      user.uchip,  # 金币数量
                                      Pool.getPoolChip(),  # 当前彩池余额
                                      fruitsOpenTimeLeft,
                                      self._openFruitIds,  # 开出的水果
                                      self._openLuckType,
                                      self._triggeredPool,  # 是否触发彩池
                                      self._triggeredPoolTotal,  # 爆彩总金额
                                      maxWinPoolList, 
                                      self._lastRoundTime,  # 到下次开奖还有多长时间
                                      user.getDayWinChips(now),  # 玩家今天赢的金币数
                                      user.winBetChip,  # 玩家本局赢的押注金币数
                                      user.winPoolChip,  # 玩家本局赢的彩池金币数
                                      weekKingList,  # 水果王周榜
                                      myKingRewardStatus,  # 玩家的水果王奖励领取状态
                                      self._top,  # 本局赢取押注金币数头名
                                      self._issueNum + 1,
                                      now)  # 当前时间

                # 记录最大赢钱的玩家
                userWinChip = user.winBetChip + user.winPoolChip
                if maxWinChip < userWinChip:
                    maxWinChip = userWinChip
                    maxWinChipUserId = userId

            else:  # 在线玩家但是观察者 (本局未押注)
                observerMsg = Sender.buildLotteryObserverMsg(Pool.getPoolChip(),
                                                             fruitsOpenTimeLeft,
                                                             self._openFruitIds,
                                                             self._openLuckType,
                                                             self._triggeredPool,
                                                             self._triggeredPoolTotal,  # 爆彩总金额
                                                             maxWinPoolList, 
                                                             self._lastRoundTime,
                                                             user.getDayWinChips(now),
                                                             weekKingList,
                                                             myKingRewardStatus,
                                                             self._top,
                                                             self._issueNum + 1,
                                                             now)
                Sender.directlySendMsg(userId, observerMsg)

        # 判断并播LED, 只播这局开奖里赢钱最多的一个玩家
        if maxWinChip >= carsconf.getLedBaseChip():
            carsled.sendLed(maxWinChipUserId, maxWinChip)

        # 更新到开奖纪录
        Lottery.appendOpenFruitsInHistory(const.FAKE_TABLE_ID, self._issueNum, self._openFruitIds, self._openLuckType, self._triggeredPool)

        # 清空水果押注实况
        self._fruitBettingChips = [0] * len(carsconf.getConf().get('fruits_id', []))

        # BI需求日志
        exceptPos = (0, 7, 11, 14, 16) #无需统计的位置
        tmp = 0 #一个变量记录开奖位置
        idsLen = len(self._openFruitIds)
        for id in self._openFruitIds:
            if idsLen <= 6 or id not in exceptPos:
                tmp =  (tmp << 5) + id
        UtilFunc.reportGameEvent(const.EVENT_GAME_LOTTERY, 1, 1, self._table.roomId, self._table.tableId,
                                 state1=idsLen,
                                 roundId=tmp,
                                 deltaChip=Pool.getPoolChip(),
                                 tableChip=len(self._bettingUsers),
                                 userChip=len(self._table.users))

        # 新的一局, 清空玩家数据, 清空押注玩家列表
        for userId, user in self._bettingUsers.iteritems():
            user.resetDataForNextRound()
        self._bettingUsers.clear()
        BetSystem._debugAcrossDaysKing = False

        self._issueNum += 1  # 局号递增
        UtilFunc.setIssueNum(self._issueNum)

    def doBroadCastFruitBetting(self):
        '''执行广播水果总注。 锁住, 跟table_call互斥'''

        # 跟上次相比, 水果总注没有变化, 不广播
        if self._lastBroadcastedFruitBettingChips == self._fruitBettingChips:
            return

        # 构建广播消息
        self._lastBroadcastedFruitBettingChips = strutil.cloneData(self._fruitBettingChips)
        mo = Sender.buildFruitBettingMsg(self._lastBroadcastedFruitBettingChips)

        # 遍历用户发广播消息
        for userId in self._table.users:
            Sender.directlySendMsg(userId, mo)

    def doBet(self, userId, issueNum, bets):
        '''玩家押注'''

        # 本局已经押注过,不能再押
        if userId in self._bettingUsers:
            return Sender.sendUserErrorMsg(userId, 'cars_bet', 'can not bet more than once in one round')

        user = self._table.users[userId]
        betConf = carsconf.getBetConf()

        # 检查参数有效性
        if not self._verifyBetParam(bets) or not issueNum:
            ftlog.debug("issueNum___", issueNum)
            return Sender.sendUserErrorMsg(userId, 'cars_bet', 'invalid bets argument')

        # 检查状态, 封盘期间不准押注, 或者程序启动还没加载好配置期间,不准押注
        if issueNum != self._issueNum or self._betStatus == const.STATE_SEAL or self._betStatus == const.STATE_INIT:
            return Sender.sendUserErrorMsg(userId, 'cars_bet', u'本局已封盘,请等待下一局!')

        # 转化, 字符串fruitId换成整数, 方便后续计算
        tmp = {}
        for fruitId in bets:
            tmp[int(fruitId)] = bets[fruitId]
        bets = tmp
        user.bets = bets
        user.fruitBetChips = {}

        # 押注金额
        betChip = 0
        for fruitId, item in bets.iteritems():
            # 每个水果的押注额, 次数
            fruitBetChip = 0
            fruitBetCount = 0

            for price, count in item.iteritems():
                iCount = int(count)
                iPrice = int(price)
                fruitBetChip += iPrice * iCount
                fruitBetCount += iCount

            # 超过水果押注上限99次
            if fruitBetCount > betConf.get('fruit_num_uplimit', 99):
                return Sender.sendUserErrorMsg(userId, 'cars_bet', 'exceed than fruit num limit')

            user.fruitBetChips[fruitId] = fruitBetChip
            betChip += fruitBetChip

        # 超过押注上限400万
        if betChip > betConf.get('bet_chip_uplimit', 4000000):
            return Sender.sendUserErrorMsg(userId, 'cars_bet', u'您押注超过上限,请重新押注!')

        if betChip == 0:
            return Sender.sendUserErrorMsg(userId, 'cars_bet', 'donot allow 0 betChip')
        user.betChip = betChip

        # 判断金币是否足够
        uchip = UtilFunc.getUserChip(userId)
        if uchip < betChip:
            return Sender.sendUserErrorMsg(userId, 'cars_bet', 'uchip is not enough')

        # 门槛金币, vip等级判断
        limitChip = carsconf.getBetConf().get('limit_chip', 0)
        vipRequired = carsconf.getBetConf().get('vip_required_for_bet', 0)
        if uchip < limitChip and user.vipLevel < vipRequired:
            text = const.BET_VIP_CHIP_LIMIT_FMT.format(VIP=int(vipRequired), CHIP=int(limitChip / 10000))
            return Sender.sendUserErrorMsg(userId, 'cars_bet', text)

        # 扣除押注金额
        clientId = user.clientId
        uchip = carschip.dnChipUpdate(userId, const.EVENT_BET_SPEND_CHIP, -betChip, clientId)

        # 放入押注玩家列表里
        self._bettingUsers[userId] = user

        # 更新水果押注实况
        for fruitId, betChip in user.fruitBetChips.iteritems():
            self._fruitBettingChips[fruitId - 1] += self._scaleBetChip(betChip)

        Sender.sendBetMsg(userId, uchip, self._fruitBettingChips)

        # BI需求日志
        for fruitId, betChip in user.fruitBetChips.iteritems():
            UtilFunc.reportGameEvent(const.EVENT_GAME_BET, userId, clientId, self._table.roomId, self._table.roomId,
                                     state1=user.vipLevel, state2=fruitId, deltaChip=betChip)

    def _scaleBetChip(self, betChip):
        '''调整押注虚假显示额度'''

        conf = carsconf.getBetConf().get('scale_display_betchip', {})
        if len(self._bettingUsers) < conf['min_users']:
            return betChip

        rate = 1
        for scaleInfo in conf['scale_infos']:
            if scaleInfo['chip'][0] <= betChip < scaleInfo['chip'][1]:
                rate = random.random() * (scaleInfo['scale'][1] - scaleInfo['scale'][0]) + scaleInfo['scale'][0]
                break

        # 向上取整到千位
        return int(math.ceil(1.0 * betChip * rate / 1000) * 1000)

    def _calcOneRoundTimeval(self, fruitNum):
        '''计算一局需要多长时间, 要判断是否中了luck, luck几个等'''

        conf = carsconf.getBetConf().get('time_interval', {})
        timeval = conf.get('ready_bet', 0) + conf.get('seal', 0) + conf.get('result', 0)

        return timeval + self._calcLotteryTime(fruitNum)

    def _calcLotteryTime(self, fruitNum):
        '''计算跑马灯转动的时间间隔'''
        conf = carsconf.getBetConf().get('time_interval', {})
        # 爆彩
        if len(self._openFruitIds) == 1 and self._openFruitIds[0] == const.CRAZE_ID:
            return conf.get('pool', 10)
        # 再来一次
        timeval = conf.get('lottery', 0)
        if len(self._openFruitIds) > 1 and self._openFruitIds[0] == const.AGAIN_ID:
            timeval += conf.get('lottery', 0) + conf.get('again', 2)
            fruitNum -= 1
        # >1说明中了LUCK
        if fruitNum > 1:  
            timeval += conf.get('luck_self', 0)  # luck本身要占的时间
            timeval += conf.get('luck_one', 0) * (fruitNum - 1)  # luck水果数的时间

        return timeval

    def _loopBetState(self):
        '''押注状态机'''

        tasklet = stackless.getcurrent()._fttask

        # 程序启动, 等待配置加载起来
        betConf = carsconf.getBetConf()
        while True:
            if len(betConf) > 0:
                break
            tasklet.sleepNb(1)

        # 下局要开出的水果
        conf = carsconf.getBetConf().get('time_interval', {})
        self._lastRoundTime = self._calcOneRoundTimeval(1)  # 当做没有LUCK, 得到一个初始的假的上轮时间
        self._nextLotteryAt = int(conf.get('ready_bet', 0) + conf.get('seal', 0) + time.time() + 0.5)
        self._fruitBettingChips = [0] * len(carsconf.getConf().get('fruits_id', []))

        ftlog.info('loopBetState start runnning:', self._fruitBettingChips, self._openFruitIds, self._lastRoundTime, self._nextLotteryAt)

        # 周期循环遍历修改状态
        while True:
            betConf = carsconf.getBetConf()

            # 设置准备阶段
            t0 = time.time()
            ftlog.debug('_loopBetState enter READY_BET status')
            self._table.doTableCall(MsgPack(), 0, 0, 'sys_set_bet_status_ready', '')

            # 准备阶段后等待 ready_bet 秒进入封盘状态
            t1 = time.time()
            tasklet.sleepNb(max(0, betConf['time_interval']['ready_bet'] - (t1 - t0)))

            t2 = time.time()
            ftlog.debug('_loopBetState enter SEAL status')
            self._table.doTableCall(MsgPack(), 0, 0, 'sys_set_bet_status_seal', '')

            # 封盘状态等待 seal 秒后, 进入开奖状态(跑马灯转动)
            t3 = time.time()
            tasklet.sleepNb(max(0, betConf['time_interval']['seal'] - (t3 - t2)))

            t4 = time.time()
            ftlog.debug('_loopBetState enter LOTTERY status')
            self._table.doTableCall(MsgPack(), 0, 0, 'sys_set_bet_status_lottery', '')

            # 开奖状态等待 lottery+luck个数*2 秒, 进入结算状态, (不用实际设置状态STATE_RESULT)
            t5 = time.time()
            lotteryTimeval = self._calcLotteryTime(len(self._openFruitIds))
            ftlog.debug('_loopBetState lotteryTimeval', self._openFruitIds, lotteryTimeval)
            tasklet.sleepNb(max(0, lotteryTimeval - (t5 - t4)))
            ftlog.debug('_loopBetState enter RESULT status')

            # 结算状态过后, 等待下一个准备时间开始
            tasklet.sleepNb(betConf['time_interval']['result'])

    def _broadCastFruitBetting(self):
        '''广播水果总注实况的循环协程'''

        tasklet = stackless.getcurrent()._fttask

        while True:
            # 启动没加载到配置, 或者封盘期间, 不广播水果总注
            if self._betStatus == const.STATE_INIT or self._betStatus == const.STATE_SEAL:
                tasklet.sleepNb(self.BROADCAST_FRUIT_BETTING_INTERVAL)
                continue

            # 每间隔2秒, 有差异化时会执行广播一次
            self._table.doTableCall(MsgPack(), 0, 0, 'sys_broadcast_fruit_betting', '')

            # 休眠2秒
            tasklet.sleepNb(self.BROADCAST_FRUIT_BETTING_INTERVAL)

    def _verifyBetParam(self, bets):
        '''检查bet命令的bets参数是否合法'''

        betRange = carsconf.getBetConf().get('bet_range', [])
        fruitIds = carsconf.getConf().get('fruits_id', [])

        if not isinstance(bets, dict):
            ftlog.debug("bets___", bets)
            return False

        for fruitId, item in bets.iteritems():
            # 非法水果id
            if int(fruitId) not in fruitIds:
                ftlog.debug("fruitId___", fruitId, "  fruitIds=", fruitIds)
                return False

            # 必须是{<price1>: count, <price2>: count, ...} 格式
            if not isinstance(item, dict):
                ftlog.debug("item___", item)
                return False

            for price, count in item.iteritems():
                # 价格不在区间内
                if int(price) not in betRange:
                    ftlog.debug("price___", price, "  betRange=", betRange)
                    return False

                # count需要是正整数
                if int(count) < 0:
                    ftlog.debug("count___", count)
                    return False

        return True

    def _calcUserWinChip(self, user, openIds, fruitsTimes):
        '''计算玩家应得奖励'''

        winChip = 0
        positionMap = carsconf.getConf().get('positionMap', {})
        ftlog.debug("_calcUserWinChip___", openIds, fruitsTimes, positionMap, user.fruitBetChips)
        # 当前本局开奖出来的水果
        for position in openIds:
            if position not in positionMap:
                continue
            openFruitId = positionMap[position]
            if openFruitId not in user.fruitBetChips:
                continue
            # 玩家在该水果上的押注金额
            fruitBetChip = user.fruitBetChips[openFruitId]

            # 按配置乘以倍数即为在该水果上的赢取金币
            winChip += fruitBetChip * fruitsTimes[position]

        return winChip

    def _openLottery(self):
        return self._openLottery_interval(1)

    def _openLottery_interval(self, tryCount=1):
        '''开奖'''

        # 利润率
        rewardRate = self._getRewardRate()

        # 根据利润率开出水果
        openIds, luckType = Lottery.openLottery(rewardRate)

        ftlog.info('_openLottery openIds=', openIds)
        return openIds, luckType

    def _getRewardRate(self):
        # 利润率
        rewardRate = 0
        if self._dayTotalBetChips > 0:
            rewardRate = 1.0 * self._dayTotalWinBetChips / self._dayTotalBetChips
        return rewardRate

