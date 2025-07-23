#! -*- coding:utf-8 -*-
# Author:   qianyong
# Created:  2016.06.21 21.56

from freetime.entity.msg import MsgPack
from poker.entity.game.tables.table_sender import TYTableSender
from poker.protocol import router

from cars.entity import const
from cars.entity import carsconf
from cars.entity.util import UtilFunc
from cars.gameplays.kingday import KingDay
from cars.gameplays.kingweek import KingWeek

class Sender(TYTableSender):
    def __init__(self, table):
        super(Sender, self).__init__(table)

    def sendQuickStartRes(self, userId, clientId, result):
        '''quickstart的响应消息'''

        mpSitRes = self.createMsgPackRes("quick_start")
        mpSitRes.updateResult(result)
        router.sendToUser(mpSitRes, userId)

    @classmethod
    def sendUserErrorMsg(self, userId, action, error):
        '''发送错误消息'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', action)
        mo.setResult('error', error)
        router.sendToUser(mo, userId)

    def sendInfoMsg(self, user, clientId, history, openFruitsPeriod, lotteryTimeLeft, uchip, poolChip, rejoin, betsInfo, issueNum, now):
        '''玩家进入牌桌时, 推送该消息, 包含客户端要用的配置, 金币等初始化消息'''

        mo = self.createMsgPackRes('table_call', 'cars_info')
        mo.setResult('conf', carsconf.getClientConf())
        mo.setResult('fruitHistory', history)
        mo.setResult('openFruitsPeriod', Sender._convertFruitsOpenTimeLeft(openFruitsPeriod))
        mo.setResult('lotteryTimeLeft', lotteryTimeLeft)
        mo.setResult('uchip', uchip)
        mo.setResult('poolchip', poolChip)
        mo.setResult('product', UtilFunc.getProductsGroup(user.userId, clientId, carsconf.getProductsConf()))  # 充值用的product
        mo.setResult('ranklist', KingDay.getTodayGameRanks(now)),
        mo.setResult('myWinChips', user.getDayWinChips())
        mo.setResult('weekKingList', KingWeek.buildDataForClient())
        mo.setResult('kingReward', KingWeek.getUserClaimStatus(user.userId))
        mo.setResult('rejoin', rejoin)
        mo.setResult('issueNum', issueNum)
        if betsInfo is not None:  # 仅在rejoin时有效
            mo.setResult('bets', betsInfo)
        router.sendToUser(mo, user.userId)

    def sendLeaveMsg(self, userId):
        '''玩家发送离开请求时的响应消息'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'cars_leave')
        mo.setResult('isOK', True)
        router.sendToUser(mo, userId)

    @classmethod
    def sendBetMsg(cls, userId, uchip, fruitBettingChips):
        '''发送押注响应消息'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'cars_bet')
        mo.setResult('uchip', uchip)
        mo.setResult('fruitBettingChips', fruitBettingChips)
        router.sendToUser(mo, userId)

    def sendClaimKingRewardMsg(self, userId, uchip):
        '''发送领取水果王奖励的响应消息'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'cars_claim_king_reward')
        mo.setResult('uchip', uchip)
        router.sendToUser(mo, userId)

    @classmethod
    def sendLotteryMsg(cls,
                       userId,
                       uchip,
                       poolchip,
                       fruitsOpenTimeLeft,
                       openIds,
                       luckType,
                       triggeredPool,
                       triggeredPoolTotal,
                       maxWinPoolList,
                       lotteryTimeLeft,
                       dayWinChips,
                       winBetChip,
                       winPoolChip,
                       weekKingList,
                       myKingReward,
                       top,
                       nextIssueNum,
                       now):
        '''发送开奖消息'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'cars_lottery')
        if uchip > 0:
            mo.setResult('uchip', uchip)
        mo.setResult('nextIssueNum', nextIssueNum)
        mo.setResult('openFruitsPeriod', cls._convertFruitsOpenTimeLeft(fruitsOpenTimeLeft))
        mo.setResult('poolchip', poolchip)
        again = const.AGAIN_ID in openIds
        mo.setResult('lottery', {"openIds": openIds, "luckType": luckType, "isBonus": triggeredPool, "again":again})
        mo.setResult('triggeredPoolTotal', triggeredPoolTotal)
        mo.setResult('maxWinPoolList', maxWinPoolList)
        mo.setResult('lotteryTimeLeft', lotteryTimeLeft)
        mo.setResult('top', top)
        mo.setResult('ranklist', KingDay.getTodayGameRanks(now))
        mo.setResult('winBetChip', winBetChip)
        mo.setResult('winPoolChip', winPoolChip)
        mo.setResult('myWinChips', dayWinChips)
        if weekKingList is not None:
            mo.setResult('weekKingList', weekKingList)
        if myKingReward is not None:
            mo.setResult('kingReward', myKingReward)

        router.sendToUser(mo, userId)

    @classmethod
    def sendFireBuyMsg(cls, userId, uchip, fireIndex):
        '''发送购买礼花的响应'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'cars_fire_buy')
        mo.setResult('uchip', uchip)
        mo.setResult('index', fireIndex)
        router.sendToUser(mo, userId)

    @classmethod
    def sendFireRewardMsg(cls, userId, fireId, timeout, name, fireIndex):
        '''发送获得礼花奖励的响应'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'cars_fire_reward')
        mo.setResult('fireId', fireId)
        mo.setResult('timeout', timeout)
        mo.setResult('name', name)
        mo.setResult('index', fireIndex)
        router.sendToUser(mo, userId)

    @classmethod
    def sendClaimFireRewardMsg(cls, userId, fireId, buyerName, reward, uchip):
        '''发送领取礼花奖励的响应'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'cars_claim_firework_prize')
        mo.setResult('gameId', const.GAME_ID)
        mo.setResult('buyerName', buyerName)
        mo.setResult('userId', userId)
        mo.setResult('fireId', fireId)
        mo.setResult('fireReward', reward)
        mo.setResult('chip', uchip)
        router.sendToUser(mo, userId)

    @classmethod
    def sendPoolListMsg(cls, userId, poolList):
        '''发送彩池中奖名单的响应'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'cars_pool_list')
        mo.setResult('poolList', poolList)
        router.sendToUser(mo, userId)

    @classmethod
    def sendClickMoreGameMsg(self, userId):
        '''用户点击"更多游戏"时,发送该消息,用于记录BI'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'click_more_game')
        mo.setResult('isOK', True)
        mo.setResult('reason', 0)
        router.sendToUser(mo, userId)

    @classmethod
    def sendSwitchGameMsg(cls, userId):
        '''用户点击切换游戏时,发送该消息,用于记录BI'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'switch_game')
        mo.setResult('isOK', True)
        mo.setResult('reason', 0)
        router.sendToUser(mo, userId)

    @classmethod
    def sendHistoryDetail(cls, userId, historyDetail):

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'cars_history_detail')
        mo.setResult('gameId', const.GAME_ID)
        mo.setResult('historyDetail', historyDetail)
        router.sendToUser(mo, userId)

    @classmethod
    def sendDebugMsg(cls, userId, action, text):
        '''发送debug响应消息'''

        mo = MsgPack()
        mo.setCmd('debug')
        mo.setResult('action', action)
        mo.setResult('text', text)
        router.sendToUser(mo, userId)

    @classmethod
    def buildChatMsg(cls, userId, userName, vipLevel, type, chatMsg, lableType):
        '''构造聊天消息'''

        mo = MsgPack()
        mo.setCmd('new_table_chat')
        mo.setResult('gameId', const.GAME_ID)
        mo.setResult('type', type)
        mo.setResult('userId', userId)
        mo.setResult('vipLevel', vipLevel)
        mo.setResult('msg', chatMsg)
        mo.setResult('name', userName)
        mo.setResult('lableType', lableType)
        return mo

    @classmethod
    def directlySendMsg(cls, userId, mo):
        '''直接发送裸消息'''

        router.sendToUser(mo, userId)

    @classmethod
    def buildLotteryObserverMsg(cls,
                                poolchip,
                                fruitsOpenTimeLeft,
                                openIds,
                                luckType,
                                triggeredPool,
                                triggeredPoolTotal,
                                maxWinPoolList,
                                lotteryTimeLeft,
                                dayWinChips,
                                weekKingList,
                                myKingReward,
                                top,
                                nextIssueNum,
                                now):
        '''构建发给观察者的开奖消息'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'cars_lottery')
        mo.setResult('poolchip', poolchip)
        mo.setResult('openFruitsPeriod', cls._convertFruitsOpenTimeLeft(fruitsOpenTimeLeft))
        again = const.AGAIN_ID in openIds
        mo.setResult('lottery', {"openIds": openIds, "luckType": luckType, "isBonus": triggeredPool, "again": again})
        mo.setResult('triggeredPoolTotal', triggeredPoolTotal)
        mo.setResult('maxWinPoolList', maxWinPoolList)
        mo.setResult('lotteryTimeLeft', lotteryTimeLeft)
        mo.setResult('myWinChips', dayWinChips)
        mo.setResult('top', top)
        mo.setResult('nextIssueNum', nextIssueNum)
        mo.setResult('ranklist', KingDay.getTodayGameRanks(now))
        if weekKingList is not None:
            mo.setResult('weekKingList', weekKingList)
        if myKingReward is not None:
            mo.setResult('kingReward', myKingReward)
        return mo

    @classmethod
    def buildFruitBettingMsg(cls, fruitBetting):
        '''构建水果总注的广播消息'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'cars_betting_chips')
        mo.setResult('fruitBettingChips', fruitBetting)

        return mo

    @classmethod
    def buildFireNotifyMsg(cls, name, fireIndex):
        '''构建放礼花的通知消息'''

        mo = MsgPack()
        mo.setCmd('table_call')
        mo.setResult('action', 'cars_fire_notify')
        mo.setResult('name', name)
        mo.setResult('index', fireIndex)
        return mo

    @classmethod
    def _convertFruitsOpenTimeLeft(cls, fruitsOpenTimeLeft):
        '''转化格式'''

        m = fruitsOpenTimeLeft.copy()
        for fruit, t in m.iteritems():
            if t == -1:
                m[fruit] = u'暂未开奖'
            else:
                if t < const.ONE_HOUR_SEC:
                    m[fruit] = u'{MIN}分前'.format(MIN=t / const.ONE_MINIUTE_SEC)
                else:
                    hour = t / const.ONE_HOUR_SEC
                    miniute = (t % const.ONE_HOUR_SEC) / const.ONE_MINIUTE_SEC
                    m[fruit] = u'{HOUR}时{MIN}分前'.format(HOUR=hour, MIN=miniute)
        return m