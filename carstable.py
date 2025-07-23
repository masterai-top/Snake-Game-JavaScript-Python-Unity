#! -*- coding:utf-8 -*-
# Author:   qianyong
# Created:  2016.06.17 14.09

from freetime.util import log as ftlog
from poker.entity.dao import onlinedata
from poker.entity.game.rooms.room import TYRoom
from poker.entity.game.tables.table import TYTable

from cars.entity import const
from cars.entity import carschip
from cars.entity import carsconf
from cars.entity import carsled
from cars.entity.util import UtilFunc
from cars.gameplays.bet import BetSystem
from cars.gameplays.chat import Chat
from cars.gameplays.debug import Debug
from cars.gameplays.fire import Fire
from cars.gameplays.kingweek import KingWeek
from cars.gameplays.lottery import Lottery
from cars.gameplays.pool import Pool
from cars.gametable.carsplayer import CarsPlayer
from cars.gametable.carssender import Sender

import time
from poker.util import strutil


class CarsTable(TYTable):
    '''水果的主逻辑'''

    CHECK_KING_LED_PERIOD = 60  # 检查水果王LED播报的时间间隔, 60秒

    def __init__(self, room, tableId):
        '''初始化'''

        super(CarsTable, self).__init__(room, tableId)

        self._sender = Sender(self)  # 发送消息的模块
        self._fire = Fire(self)  # 礼花模块
        self._chat = Chat(self)  # 聊天模块
        self._bet = BetSystem(self)  # 押注模块

        self._users = {}  # 在线玩家列表

        # 间隔60秒,检查广播头天的king
        UtilFunc.callLater(self.CHECK_KING_LED_PERIOD, self._loopLedYesterdayKing)

    @property
    def users(self):
        return self._users

    @property
    def chat(self):
        return self._chat

    @property
    def fire(self):
        return self._fire

    def _doSit(self, msg, userId, seatId, clientId):
        '''玩家操作, 尝试再当前的某个座位上坐下'''

        # 属于本局已下注,但退出了,本局还没开奖又重连进来的. 这类用户,在本局开奖前不能再下注
        rejoin = False
        betsInfo = None  # 押注情况
        if userId in self._bet.bettingUsers:
            user = self._bet.bettingUsers[userId]
            user.clientId = clientId  # 更新clientId, 因为用户可能更换成其他客户端登陆, clientId会变化

            betsInfo = user.bets  # 押注情况
            rejoin = True  # 是否押注了后本局还没开奖就又重登陆进来
        else:
            vipLevel = UtilFunc.getUserVipLevel(userId)
            name, purl = UtilFunc.getUserNameAndPurl(userId)
            user = CarsPlayer(self, userId, name, vipLevel, clientId)

        now = int(time.time())

        # 西瓜,数字7开奖时间点离现在的时间多少
        fruitsOpenTimeLeft = strutil.cloneData(Lottery.getFruitsLastOpenTime())
        for fruitId in fruitsOpenTimeLeft:
            if fruitsOpenTimeLeft[fruitId] == 0:
                fruitsOpenTimeLeft[fruitId] = -1  # -1表示到现在还没开出过对应的水果
            else:
                fruitsOpenTimeLeft[fruitId] = now - fruitsOpenTimeLeft[fruitId]

        # 下次开奖的时间还有多长时间
        lotteryTimeLeft = max(0, self._bet.nextLotteryAt - now)

        # 玩家金币余额, 彩池余额
        uchip = UtilFunc.getUserChip(userId)
        poolChip = Pool.getPoolChip()

        # 设置onlineLoc, 在玩家掉线时, 大厅才能发通知消息到GR, GR再通知到GT
        onlinedata.addOnlineLoc(userId, self.roomId, self.tableId, const.FAKE_SEAT_ID)

        self._sender.sendQuickStartRes(userId, clientId, {"isOK": True, 'reason': TYRoom.ENTER_ROOM_REASON_OK})
        historyMaxLen = carsconf.getHistoryConf().get('simple_num', 0)
        self._sender.sendInfoMsg(user, clientId,
                                 Lottery.getOpenFruitsHistory(const.FAKE_TABLE_ID)[:historyMaxLen],
                                 fruitsOpenTimeLeft,
                                 lotteryTimeLeft,
                                 uchip,
                                 poolChip,
                                 rejoin,
                                 betsInfo,
                                 self._bet.issueNum,
                                 now)

        # 发送info后, 再放用户到"在线用户列表"中, 避免在info消息之前先发了fruit_lottery消息
        self._users[userId] = user

        # BI需求日志
        ftlog.info('BI.Info userId=', userId, 'vipLevel=', user.vipLevel)

    def _doLeave(self, msg, userId, clientId):
        '''
        玩家操作, 尝试离开当前的桌子
        实例桌子可以覆盖 _doLeave 方法来进行自己的业务逻辑处理
        '''
        ftlog.debug('_doLeave, userId=', userId)
        self._doLeaveCars(userId, TYRoom.LEAVE_ROOM_REASON_ACTIVE)

    def _doStandUp(self, msg, userId, seatId, reason, clientId):
        '''
        玩家操作, 尝试离开当前的座位
        子类需要自行判定userId和seatId是否吻合
        '''
        ftlog.debug('_doStandUp, userId=', userId)
        self._doLeaveCars(userId, TYRoom.LEAVE_ROOM_REASON_ACTIVE)

    def _doTableManage(self, msg, action):
        '''桌子内部处理所有的table_manage命令'''

        result = {'action': action, 'isOK': True}
        if action == 'leave':
            userId = msg.getParam('userId')
            reason = msg.getParam('reason')
            self._doLeaveCars(userId, reason)
            ftlog.debug('_doTableManage user', userId, 'leave table, total users count', len(self._users), 'reason=', reason)

        return result

    def _doLeaveCars(self, userId, reason):
        '''离开水果'''

        # 记录玩家的游戏时间
        if userId in self._users:
            user = self._users[userId]
            timeval = time.time() - user.enterGameAt
            UtilFunc.incrPlayerGameTime(userId, timeval)

            # 在线玩家中去除用户; 押注玩家列表里不能去除, 影响押注结算
            del self._users[userId]
            self._sender.sendLeaveMsg(userId)

            # 移除onlineLoc
            onlinedata.removeOnlineLoc(userId, self.roomId, self.tableId)

        ftlog.info('_doLeaveCars user', userId, 'leave table, total users count', len(self._users), 'reason=', reason)

    def getUser(self, userId):
        '''根据userId返回user对象'''

        if userId in self._users:
            return self._users[userId]
        return None

    def _doTableCall(self, msg, userId, seatId, action, clientId):
        '''
        桌子同步安全操作方法
        桌子内部处理所有的table_call命令
        实例桌子可以覆盖 _doTableCall 方法来进行自己的业务逻辑处理
        子类需要自行判定userId和seatId是否吻合
        '''

        if ftlog.is_debug():
            ftlog.debug('self._doTableCall action=', action, 'userId=', userId, 'msg=', msg)

        # 这里是系统自己发出的table_call
        if action == 'sys_fruit_fire':  # 系统放礼花
            return self.doSysFire()

        elif action == 'sys_chat_define_msg':  # 聊天发送系统预置消息
            text = msg.getParam('text')
            return self.doSysChatDefineMsg(text)

        elif action == 'sys_set_bet_status_ready':
            return self.doSetBetStatusReady()

        elif action == 'sys_set_bet_status_seal':  # 设置封盘状态
            return self.doSetBetStatusSeal()

        elif action == 'sys_set_bet_status_lottery':  # 设置开奖状态
            return self.doSetBetStatusLottery()

        elif action == 'sys_broadcast_fruit_betting':  # 广播水果总注
            return self.doBroadcastFruitBetting()

        # 下面是用户发出的table_call
        # 用户发送table_call命令前应该先quick_start过了, 在self._users中必定有值
        if userId not in self._users:
            if action == 'leave' or 'cars_leave':  # 无视leave
                self._sender.sendLeaveMsg(userId)
            ftlog.warn('tablecall logic error', userId, 'not in self._users')
            return self._sender.sendUserErrorMsg(userId, action, u'您已掉线,请重进游戏!')

        user = self._users[userId]

        if action == 'cars_bet':
            bets = msg.getParam('bets')
            issueNum = msg.getParam('issueNum')
            return self.doBet(userId, issueNum, bets)

        elif action == 'cars_leave':
            return self._doLeaveCars(userId, TYRoom.LEAVE_ROOM_REASON_ACTIVE)

        elif action == 'cars_claim_king_reward':
            return self.doClaimKingReward(userId)

        elif action == 'cars_fire_buy':
            index = msg.getParam('index')
            return self.doFireBuy(userId, index)

        elif action == 'cars_claim_firework_prize':
            fireId = msg.getParam('fireId', 0)
            fireId = int(fireId)
            return self._fire.claimFireReward(user, fireId)

        elif action == 'new_table_chat':
            chatType = msg.getParam('type')
            chatMsg = msg.getParam('msg')
            return self.doChat(userId, chatType, chatMsg)

        elif action == 'cars_pool_list':
            return self.doGetPoolList(userId)

        elif action == 'cars_history_detail':
            return self.doGetHistoryDetail(user)

        elif action == 'click_more_game':
            UtilFunc.reportGameEvent(const.EVENT_OPEN_MORE_GAMES, userId, user.clientId, self.roomId, self.tableId)
            return Sender.sendClickMoreGameMsg(userId)

        elif action == 'switch_game':
            switchGameId = msg.getParam('switchGameId')
            UtilFunc.reportGameEvent(const.EVENT_SWITCH_GAME, userId, user.clientId, self.roomId, self.tableId,
                                     deltaChip=switchGameId)
            return Sender.sendSwitchGameMsg(userId)

    def doBet(self, userId, issueNum, bets):
        '''玩家押注'''

        self._bet.doBet(userId, issueNum, bets)

    def doClaimKingReward(self, userId):
        '''领取水果王奖励'''

        status = KingWeek.getUserClaimStatus(userId)
        if not status['canClaim']:
            return Sender.sendUserErrorMsg(userId, 'cars_claim_king_reward', 'can not claim')

        KingWeek.setUserClaimedStatus(userId, True)

        reward = carsconf.getKingConf().get('reward', 0)
        user = self._users[userId]

        # 领取水果王奖励涨的钱, 不会计入水果王当天排行里
        uchip = carschip.dnChipUpdate(userId, const.EVENT_KING_REWARD, reward, user.clientId)

        self._sender.sendClaimKingRewardMsg(userId, uchip)

    def doFireBuy(self, userId, index):
        '''购买礼花'''

        user = self._users[userId]
        self._fire.buyFire(user, index, user.clientId)

    def doChat(self, userId, chatType, msg):
        '''玩家发送聊天'''

        self._chat.userChat(userId, chatType, msg)

    def doGetPoolList(self, userId):
        '''获取彩池中奖列表'''

        poolList = Pool.getPoolList()
        Sender.sendPoolListMsg(userId, poolList)

    def doGetHistoryDetail(self, user):
        '''获取详细的历史记录'''

        history = Lottery.getOpenFruitsHistory(const.FAKE_TABLE_ID)
        history = history[:]
        for item in history:
            issueNum = item['issueNum']
            if issueNum in user.winHistory:
                item['winChip'] = user.winHistory[issueNum]
            else:
                item['winChip'] = 0
        Sender.sendHistoryDetail(user.userId, history)

    def doSysFire(self):
        '''系统发放礼花'''

        self._fire.sysFire()

    def doSysChatDefineMsg(self, text):
        '''系统发送预置的系统消息到聊天频道'''

        self._chat.broadcastSysChat(text, const.CHAT_LABLE_NOMAL_TYPE)

    def doSetBetStatusReady(self):
        '''设置准备状态'''

        return self._bet.setTableReadyState()

    def doSetBetStatusSeal(self):
        '''设置封盘状态'''

        return self._bet.setTableSealState()

    def doSetBetStatusLottery(self):
        '''设置开奖状态'''

        return self._bet.setTableLotteryState()

    def doBroadcastFruitBetting(self):
        '''广播水果总注'''

        return self._bet.doBroadCastFruitBetting()

    def _loopLedYesterdayKing(self):
        '''周期性的广播头一天的水果王LED'''

        # 时间到了,则发送水果王LED
        now = time.time()
        st = time.localtime(now)
        if st.tm_min == carsconf.getLedKingAtMinute():
            user = KingWeek.getSpecificDayKing(now - const.ONE_DAY_SEC)  # 获取头一天的水果王
            if user is not None:
                ftlog.debug('sendKingLed', user)
                carsled.sendKingLed(user['userId'], user['name'], carsconf.getKingConf().get('reward', 0))

        # 下次再调度
        UtilFunc.callLater(self.CHECK_KING_LED_PERIOD, self._loopLedYesterdayKing)

    def doDebug(self, msg):
        '''debug辅助测试'''

        Debug.doDebug(msg)
