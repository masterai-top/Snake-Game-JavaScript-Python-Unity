#! -*- coding:utf-8 -*-
# Author:   qianyong
# Created:  2016.06.21 21.43

from freetime.util import log as ftlog
from poker.entity.game.tables.table_player import TYPlayer

from cars.gameplays.kingday import KingDay
from cars.entity.util import UtilFunc
from cars.entity import carsconf

import json
import time


class CarsPlayer(TYPlayer):
    '''player'''

    def __init__(self, table, userId, name, vipLevel, clientId=''):
        super(CarsPlayer, self).__init__(table, 1)
        self._userId = userId
        self._name = name
        self._vipLevel = vipLevel  # vip等级, 做后续打印日志用,不能用做判断游戏行为标准,比如判断是否能聊天等
        self._clientId = clientId  # 玩家client id
        self._bets = {}  # 玩家当前这局押注情况: 某个水果在什么价位押注多少次, <fruitId: {<price>: count, ...}>
        self._fruitBetChips = {}  # 玩家当前局每个水果押了多少钱, <fruitId: chip>
        self._betChip = 0  # 玩家当前局总押注金额
        self._uchip = 0  # 在开奖时, 临时用一下的变量,保存玩家的金币。 这个值不是实时更新的,仅在开奖加金币时更新一下
        self._winBetChip = 0  # 玩家在本局开奖时押注要赢的金币
        self._winPoolChip = 0  # 玩家在本局开奖时彩池要赢的金币
        self._dayWinChips = {}  # 玩家在哪天总计赢的金币数, key是日期0612, value是赢的金币数
        self._lastChatAt = 0  # 玩家上次发送聊天消息的时间
        self._enterGameAt = time.time()  # 玩家进入游戏的时间
        self._winHistory = None  # 中奖记录 dict[issueNum, winChip]
        self._initWinHistory()

    @property
    def userId(self):
        return self._userId

    @property
    def name(self):
        return self._name

    @property
    def vipLevel(self):
        return self._vipLevel

    @property
    def clientId(self):
        return self._clientId

    @clientId.setter
    def clientId(self, value):
        self._clientId = value

    @property
    def bets(self):
        return self._bets

    @bets.setter
    def bets(self, value):
        self._bets = value

    @property
    def uchip(self):
        return self._uchip

    @uchip.setter
    def uchip(self, value):
        self._uchip = value

    @property
    def winBetChip(self):
        return self._winBetChip

    @winBetChip.setter
    def winBetChip(self, value):
        self._winBetChip = value

    @property
    def winPoolChip(self):
        return self._winPoolChip

    @winPoolChip.setter
    def winPoolChip(self, value):
        self._winPoolChip = value

    @property
    def fruitBetChips(self):
        return self._fruitBetChips

    @fruitBetChips.setter
    def fruitBetChips(self, value):
        self._fruitBetChips = value

    @property
    def betChip(self):
        return self._betChip

    @betChip.setter
    def betChip(self, value):
        self._betChip = value

    @property
    def lastChatAt(self):
        return self._lastChatAt

    @lastChatAt.setter
    def lastChatAt(self, value):
        self._lastChatAt = value

    @property
    def enterGameAt(self):
        return self._enterGameAt

    @enterGameAt.setter
    def enterGameAt(self, value):
        self._enterGameAt = value

    @property
    def winHistory(self):
        return self._winHistory

    def _initWinHistory(self):
        if self._winHistory is None:
            data = UtilFunc.getUserWinHistory(self._userId)
            ftlog.debug(self._userId, data)
            self._winHistory = {}
            if data:
                tmp = json.loads(data)
                for issueNum, chip in tmp.iteritems():
                    self._winHistory[int(issueNum)] = chip

        return self._winHistory

    def updateWinHistory(self, issueNum, winChip):
        '''更新获胜记录'''

        self._winHistory[issueNum] = winChip
        if len(self._winHistory) > carsconf.getHistoryConf().get('num', 0):
            del self._winHistory[min(self._winHistory.keys())]
        UtilFunc.setUserWinHistory(self._userId, json.dumps(self._winHistory))

    def resetDataForNextRound(self):
        '''为下一局开奖重置相关数据'''

        self._bets.clear()
        self._fruitBetChips.clear()
        self._betChip = 0
        self._uchip = 0
        self._winBetChip = 0
        self._winPoolChip = 0

    def getDayWinChips(self, now=None):
        '''获取今日总赢取金币数'''

        if now is None:
            now = time.time()

        date = time.strftime("%m%d", time.localtime(now))
        if date not in self._dayWinChips:
            self._dayWinChips[date] = KingDay.getUserTodayWinChips(self._userId, now)

        return self._dayWinChips[date]

    def addDayWinChips(self, deltaChips, now):
        '''添加今日赢取金币数'''

        # redis为该用户添加赢取金币数
        dayWinChips = KingDay.addWinChip(self._userId, deltaChips, now)

        # 本地变量也同步添加赢取金币数
        date = time.strftime("%m%d", time.localtime(now))
        self._dayWinChips[date] = dayWinChips
