#! -*- coding:utf-8 -*-
# Author:   qianyong
# Created:  2016.06.27 18.05

from freetime.util import log as ftlog
from poker.entity.dao import userchip, userdata, gamedata, tabledata, daobase

from cars.entity import const
from cars.entity import carsconf

import json
import random
import time


class Pool(object):
    '''彩池功能'''

    _poolchip = None  # 彩池余额, 本地缓存变量, 不用每次从redis读取
    _poolList = None  # 彩池中奖名单
    _poolListKey = 'poollist:%d' % const.GAME_ID

    # 测试用
    _debugTriggeredPool = False

    @classmethod
    def getPoolChip(cls):
        '''获取彩池余额'''

        if cls._poolchip is None:
            chip = tabledata.getTableAttr(const.ROOM_ID, const.FAKE_TABLE_ID, 'poolchip')

            # redis里没有,说明是第一次,初始化彩池余额
            if chip is None or chip == 0 or chip == '':
                chip = carsconf.getPoolConf().get('init_chip', 0)
                tabledata.setTableAttr(const.ROOM_ID, const.FAKE_TABLE_ID, 'poolchip', chip)

            cls._poolchip = chip

        return cls._poolchip

    @classmethod
    def incrPoolChipByDeltaUserChip(cls, deltaUserChip):
        '''根据用户金币变动额, 彩池余额按照抽水率跟随变动'''

        poolChip = cls.getPoolChip()
        if deltaUserChip == 0:
            return poolChip

        # 配置信息中根据当前彩池余额找到对应的抽水率
        rate = 0
        rateInfos = carsconf.getPoolConf().get('choushui_rate', [])
        for rateInfo in rateInfos:
            if poolChip >= rateInfo['minChip'] and (poolChip < rateInfo['maxChip'] or rateInfo['maxChip'] == -1):
                rate = rateInfo['rate']
                break

        # 按照抽水率的彩池应该涨的数额; 玩家输了彩池涨, 玩家赢了彩池降, 所以取反
        deltaPoolChip = -int(rate * deltaUserChip)

        return cls.incrPoolChipByDeltaPoolChip(deltaPoolChip)

    @classmethod
    def incrPoolChipByDeltaPoolChip(cls, deltaPoolChip):
        '''根据彩池变动额, 直接增减彩池余额'''

        baseChip = carsconf.getPoolConf().get('base_chip', 0)
        if cls.getPoolChip() + deltaPoolChip < baseChip:
            tabledata.setTableAttr(const.ROOM_ID, const.FAKE_TABLE_ID, 'poolchip', baseChip)
            cls._poolchip = baseChip
        else:
            cls._poolchip = tabledata.incrTableAttr(const.ROOM_ID, const.FAKE_TABLE_ID, 'poolchip', deltaPoolChip)

        return cls._poolchip

    @classmethod
    def triggerPoolChip(cls, rewardRate):
        '''根据开出的水果判断是否触发彩池, 返回 true/false, <times>'''

        cond = carsconf.getPoolConf().get('trigger_condition', {})
        rewardTimes = carsconf.getPoolConf().get('reward_times', 1)

        # 如果有测试设置触发彩池, 则用测试的, 然后重置
        if cls._debugTriggeredPool:
            cls._debugTriggeredPool = False
            return True, rewardTimes

        if cls.getPoolChip() >= cond['pool_needed'] and rewardRate <= cond['max_reward_rate'] and random.random() <= cond['probability']:
            return True, rewardTimes
            
        return False, 0

    @classmethod
    def getPoolList(cls):
        '''获取彩池中奖名单'''

        if cls._poolList is None:
            maxLen = carsconf.getPoolConf().get('pool_list_len', 0)
            poolList = daobase.executeMixCmd('LRANGE', cls._poolListKey, 0, maxLen - 1)
            if poolList is None:
                poolList = []

            # 挨个做json解析
            for i in xrange(len(poolList)):
                poolList[i] = json.loads(poolList[i])

            cls._poolList = poolList

        return cls._poolList

    @classmethod
    def appendPoolList(cls, poolChip, rewardChip):
        '''记录彩池奖励事件到彩池中奖名单里'''

        # 保存到redis
        date = time.strftime('%Y-%m-%d %H:%M', time.localtime())
        item = {'date': date, 'rewardChip': rewardChip, 'poolChip': poolChip}
        daobase.executeMixCmd('LPUSH', cls._poolListKey, json.dumps(item))

        # 判断redis里的长度
        maxLen = carsconf.getPoolConf().get('pool_list_len', 1)
        length = daobase.executeMixCmd('LLEN', cls._poolListKey)
        if length > maxLen * 2:  # 乘以2, 以便减少redis操作io次数
            daobase.executeMixCmd('LTRIM', cls._poolListKey, 0, maxLen - 1)

        # 判断本地变量里的长度
        poolList = cls.getPoolList()
        # poolList.insert(0, item)
        poolList[0:0] = (item,)
        if len(poolList) > maxLen:
            del poolList[maxLen:]

        return poolList
