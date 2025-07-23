#! -*- coding:utf-8 -*-
# Author:   qianyong
# Created:  2016.06.21 10.08

from freetime.util import log as ftlog
from poker.entity.dao import daobase, tabledata

from cars.entity import const
from cars.entity import carsconf
from cars.entity.util import UtilFunc

import random
import json
import time
from poker.util import strutil


class Lottery(object):
    '''开奖算法'''

    _history = None  # 开奖历史纪录, 初始化为None, 后面再从redis读数据初始化为列表
    _fruitsLastOpenTime = {}  # 西瓜,数字7的最近开奖时间  <fruitId: time>

    # 测试补丁
    _debugNextOpenId = -1 # 开奖位置
    _debugAgain = False # 再来一次
    _debugLuckType = '' # 开奖位置

    @classmethod
    def openLottery(cls, rewardRate):
        '''开奖'''

        openRate = carsconf.getOpenRateConf()
        detailList = openRate.get('detail_rates', {})
        luckConfig = openRate.get('luck', {})
        luckMaxRewardRate = openRate.get('luck_max_reward_rate', 0.88)
        result = []
        # 再来一次
        if cls._debugAgain or random.random() <= openRate.get('again_rate', 0.1):
            cls._debugAgain = False
            result.append(const.AGAIN_ID) 
        # luck
        if cls._debugLuckType or (rewardRate <= luckMaxRewardRate and random.random() <= luckConfig['rate']): 
            group = cls._debugLuckType or UtilFunc.randomChoiceByWeight(luckConfig['group_rates'])
            cls._debugLuckType = ''
            luckIds = []
            for car in luckConfig['groups'][group]:
                pos = UtilFunc.randomChoiceByWeight(detailList[car])
                luckIds.append(int(pos))
            random.shuffle(luckIds)
            return result+[const.LUCK_ID]+luckIds, group
        # 单次开奖
        normalList = openRate.get('normal_rates', {})
        car = UtilFunc.randomChoiceByWeight(normalList)
        pos = UtilFunc.randomChoiceByWeight(detailList[car])
        if cls._debugNextOpenId != -1:
            pos = cls._debugNextOpenId
            cls._debugNextOpenId = -1
        result.append(int(pos))
        return result, ""

    @classmethod
    def appendOpenFruitsInHistory(cls, tableId, issueNum, openIds, luckType, isBonus=False):
        '''添加开出的水果到历史开奖纪录'''

        item = {"openIds": openIds, "luckType": luckType, "issueNum": issueNum, "isBonus": isBonus}

        # 存到redis
        redisKey = cls._getHistoryKey(tableId)
        daobase.executeMixCmd('LPUSH', redisKey, json.dumps(item))

        # redis里的数据是否超出上限
        maxLen = carsconf.getHistoryConf().get('num', 1)
        length = daobase.executeMixCmd('LLEN', redisKey)
        if length > maxLen * 2:  # 乘以2, 以便减少redis操作io次数
            daobase.executeMixCmd('LTRIM', redisKey, 0, maxLen - 1)

        # 存到本地变量
        localHistory = cls.getOpenFruitsHistory(tableId)
        localHistory[0:0] = (item,)
        # localHistory.insert(0, item)
        if len(localHistory) > maxLen:
            del localHistory[maxLen:]

        # 如果开出有西瓜,数字7, 需要纪录西瓜, 数字7的最近开奖时间
        now = int(time.time())
        lastTimeFruitIds = carsconf.getHistoryConf().get('save_last_time_for_fruits', [])
        for fruitId in openIds:
            if fruitId in lastTimeFruitIds:
                # 存到redis
                attrname = 'open%sAt' % fruitId
                tabledata.setTableAttr(const.ROOM_ID, const.FAKE_TABLE_ID, attrname, now)

                # 存到本地变量
                cls._fruitsLastOpenTime[fruitId] = now

    @classmethod
    def getFruitsLastOpenTime(cls):
        '''
        获得西瓜, 数字7的最近开奖时间
        返回 {7: 12341234, 8: 2341234}  //水果id对应的最近开奖时间
        '''

        # 配置里配的我们要纪录开奖时间的西瓜, 数字7的ID
        lastTimeFruitIds = carsconf.getHistoryConf().get('save_last_time_for_fruits', [])

        # 本地变量没保存到有, 则从redis读出
        if len(cls._fruitsLastOpenTime) < len(lastTimeFruitIds):
            attrs = []
            for fruitId in lastTimeFruitIds:
                attrs.append('open%sAt' % fruitId)
            values = tabledata.getTableAttrs(const.ROOM_ID, const.FAKE_TABLE_ID, attrs)
            if not values:
                values = [0] * len(lastTimeFruitIds)

            for i in xrange(len(lastTimeFruitIds)):
                fruitId = lastTimeFruitIds[i]
                cls._fruitsLastOpenTime[fruitId] = values[i] if values[i] is not None else 0

            ftlog.debug(cls._fruitsLastOpenTime, values)

        return cls._fruitsLastOpenTime

    @classmethod
    def getFruitLastOpenTimeLeft(cls, now):
        '''西瓜,数字7开奖时间点离现在的时间多少'''

        fruitsOpenTimeLeft = strutil.cloneData(cls.getFruitsLastOpenTime())
        for fruitId in fruitsOpenTimeLeft:
            if fruitsOpenTimeLeft[fruitId] == 0:
                fruitsOpenTimeLeft[fruitId] = -1  # -1表示到现在还没开出过对应的水果
            else:
                fruitsOpenTimeLeft[fruitId] = now - fruitsOpenTimeLeft[fruitId]
        return fruitsOpenTimeLeft

    @classmethod
    def getOpenFruitsHistory(cls, tableId):
        '''获取历史开奖纪录'''

        # 本地变量没有时才从redis去获取
        if cls._history is None:
            redisKey = cls._getHistoryKey(tableId)

            num = carsconf.getHistoryConf().get('num', 1)
            items = daobase.executeMixCmd('LRANGE', redisKey, 0, num - 1)
            if items is None:
                items = []

            # 挨个做json解析
            for i in xrange(len(items)):
                items[i] = json.loads(items[i])

            cls._history = items

        return cls._history

    @classmethod
    def _getHistoryKey(cls, tableId):
        '''获取保存历史纪录的key'''

        return 'cars:%d:%d:openfruits_history1' % (const.GAME_ID, tableId)

