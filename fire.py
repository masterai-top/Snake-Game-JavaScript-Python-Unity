#! -*- coding:utf-8 -*-
# Author:   qianyong
# Created:  2016.06.28 14.20

from freetime.entity.msg import MsgPack
from freetime.util import log as ftlog
from freetime.core.lock import locked

from cars.entity import carsconf
from cars.entity.util import UtilFunc
from cars.entity import carschip
from cars.entity import const
from cars.gameplays.pool import Pool
from cars.gametable.carssender import Sender

import random
import stackless
import time


class Fire(object):
    '''礼花功能'''

    fireId = 0  # 礼花ID, 每次放礼花时，自增
    fires = {}  # 放过的礼花列表, 需要互斥访问 dict[fireId, dict[type: issys, users: dict[userId, reward]]]

    def __init__(self, table):
        self._table = table
        '''@type: cars.gametable.carstable.CarsTable'''  # 向pycharm暗示table的类型为CarsTable

        self._fireAt = 0  # 上次什么时间发过礼花
        self._guixie = ''  # 玩家要发的跪谢土豪的聊天消息

        # 10秒后启动系统礼花的检测发放
        UtilFunc.callLater(10, self._sysFireLoop)

    @property
    def fireAt(self):
        return self._fireAt

    @property
    def guixie(self):
        return self._guixie

    def buyFire(self, user, fireIndex, clientId):
        '''购买礼花'''

        table, userId, userName = user.table, user.userId, user.name
        fireUserConf = carsconf.getFireConf().get('user', {})
        counts = fireUserConf.get('count', [])

        if not isinstance(fireIndex, int) or fireIndex < 0 or fireIndex >= len(counts):
            return Sender.sendUserErrorMsg(userId, 'cars_fire_buy', 'index is invalid')

        # 玩家自己花钱购买礼花
        price = fireUserConf.get('price', 0) * counts[fireIndex]
        uchip = UtilFunc.getUserChip(userId)
        if uchip < price:
            return Sender.sendUserErrorMsg(userId, 'cars_fire_buy', 'chip is not enough')
        user.uchip = carschip.dnChipUpdate(userId, const.EVENT_FIRE_BUY, -price, clientId)

        UtilFunc.callLater(0, self._executeFire, False, fireIndex, userId, userName,
                           user.uchip, const.EVENT_USER_FIRE_REWARD)

    def sysFire(self):
        '''系统发放礼花'''

        fireSysConf = carsconf.getFireConf().get('system', {})
        fireIndex = fireSysConf.get('fire_index', 0)

        now = time.time()
        fireUserConf = carsconf.getFireConf().get('user', {})
        counts = fireUserConf.get('count', [])

        # 系统花彩池里的钱来购买礼花
        price = fireUserConf.get('price', 0) * counts[fireIndex]
        Pool.incrPoolChipByDeltaPoolChip(-price)

        name = fireSysConf.get('guixie_name', '')
        self._guixie = const.CHAT_GUIXIE_FMT.format(name=name)
        self._fireAt = now
        self._broadFireChat(name, True, fireIndex)

        # 放在协程里执行，避免死锁
        UtilFunc.callLater(0, self._executeFire, True, fireIndex, -1, name, 0, const.EVENT_SYS_FIRE_REWARD)


    def _executeFire(self, isSysFire, fireIndex, userId, userName, uchip, eventId):
        now = time.time()

        self._guixie = const.CHAT_GUIXIE_FMT.format(name=userName)
        self._fireAt = now
        self._broadFireChat(userName, isSysFire, fireIndex)

        if userId > 0:
            Sender.sendFireBuyMsg(userId, uchip, fireIndex)

        # 发放礼花奖励给其他玩家
        fireId = self._genFireId()
        toUserIds, extraChouShui = self._sendFireReward(userName, isSysFire, fireIndex, userId,
                                                        const.EVENT_SYS_FIRE_REWARD, now, fireId)
        # 向其他未收到奖励的玩家广播通知: 有人放礼花啦
        self._sendFireNotify(userName, fireIndex, toUserIds)

        self._saveFireRewardsInfo(fireId, isSysFire, fireIndex, userName, toUserIds)
        UtilFunc.callLater(carsconf.getFireConf().get('timeout', 0) + 1, self._timeoutDelFireRewardsInfo, fireId)

    def claimFireReward(self, user, fireId):
        '''玩家领取礼花奖励'''

        rewardChip, isSys, fireIndex, buyerName = self._checkAndDel(fireId, user.userId)
        if rewardChip == 0:
            return Sender.sendErrorMsgWithoutTableId(user.userId, 'cars_claim_firework_prize', u'下次手速快点哦～')

        # 发送奖励
        eventId = const.EVENT_USER_FIRE_REWARD
        if isSys:
            eventId = const.EVENT_SYS_FIRE_REWARD
        user.uchip = carschip.dnChipUpdate(user.userId, eventId, rewardChip, user.clientId)
        Sender.sendClaimFireRewardMsg(user.userId, fireId, buyerName, rewardChip, user.uchip)

        # 确定聊天消息模版
        conf = carsconf.getFireConf()
        if isSys:
            rewardChatMsgFmt = conf['system']['reward_msg']
        else:
            rewardChatMsgFmt = conf['user']['reward_msgs'][fireIndex]

        # 聊天频道里的消息,显示自己收到了谁发的多少礼花奖励
        rewardChatMsg = rewardChatMsgFmt.format(name=buyerName, chip=rewardChip)
        self._table.chat.sendSysChatToUser(rewardChatMsg, const.CHAT_LABLE_NOMAL_TYPE, user.userId)

    def _broadFireChat(self, userName, isSys, fireIndex):
        '''广播系统消息, 有人放了礼花'''

        conf = carsconf.getFireConf()

        if isSys:
            msg = conf['system']['broadcast_sys_msg']
            lableType = const.CHAT_LABLE_NOMAL_TYPE
        else:
            msg = conf['user']['broadcast_sys_msgs'][fireIndex].format(name=userName)
            lableType = conf['user']['msg_lable_types'][fireIndex]

        self._table.chat.broadcastSysChat(msg, lableType)

    def _sendFireNotify(self, name, fireIndex, excludeUserIds):
        '''
        广播有人放礼花的通知消息

        :param name: 放礼花人的名字
        :param fireIndex: 哪一种礼花, 0, 1, 2
        :param excludeUserIds: 排除的userid列表,不给这里面的人发消息
        :return:
        '''

        mo = Sender.buildFireNotifyMsg(name, fireIndex)

        for userId in self._table.users:
            if userId not in excludeUserIds:
                Sender.directlySendMsg(userId, mo)

    def _sendFireReward(self, userName, isSys, fireIndex, excludeUserId, eventId, now, fireId):
        '''
        根据配置挑选用户广播礼花奖励, 排除excludeUserId

        :param userName: 买礼花人的名字。聊天频道发的奖励消息需要
        :param isSys: 是否系统放的礼花。=> 系统的礼花的聊天频道奖励消息不一样
        :param fireIndex: 哪种礼花, 0, 1, 2
        :param excludeUserId: 排除掉的用户ID, 通常是在玩家购买礼花时,购买者ID
        :param eventId: 金流事件ID
        :param now: 当前时刻
        :return: 返回两个数据: 发送过的所有玩家ID, 是一个集合; 额外抽水
        '''

        conf = carsconf.getFireConf()

        # 确定聊天消息模版
        if isSys:
            rewardChatMsgFmt = conf['system']['reward_msg']
        else:
            rewardChatMsgFmt = conf['user']['reward_msgs'][fireIndex]

        # 奖励模式. 格式{"small": {"chip": 123, "number": 1}, "big": {...}}
        if isSys:
            rewardConf = conf['system']['reward']
        else:
            rewardConf = conf['user']['rewards'][fireIndex]

        userIds = self._table.users.keys()  # 总用户
        toUserIds = {}  # 向哪些玩家发送了奖励

        # 发送奖励
        shouldSendRewardChip = 0
        totalSendRewardChip = 0
        for rewardType, oneRewardConf in rewardConf.iteritems():
            rewardChip = oneRewardConf.get('chip', 0)
            number = oneRewardConf.get('number', 0)
            if rewardChip <= 0 or number <= 0:
                continue

            shouldSendRewardChip += rewardChip * number  # 累计应该发出的金币奖励

            # 聊天频道里的消息,显示自己收到了谁发的多少礼花奖励
            rewardChatMsg = rewardChatMsgFmt.format(name=userName, chip=rewardChip)

            currToUserIds = self._sendRewardToUsers(userName, fireIndex, rewardChatMsg, rewardChip,
                                                    number, userIds, excludeUserId, eventId, now, fireId)
            totalSendRewardChip += rewardChip * len(currToUserIds)  # 总共实际发出的金币奖励
            toUserIds.update(currToUserIds)

        return toUserIds, shouldSendRewardChip - totalSendRewardChip

    def _sendRewardToUsers(self, name, fireIndex, rewardChatMsg, rewardChip, number, userIds, excludeUserId, eventId, now, fireId):
        '''
        从userIds中随机选择number个用户发放rewardChip的金币奖励

        :param name: 放礼花的人的名字
        :param fireIndex: 哪种礼花, 0, 1, 2
        :param rewardChip: 要发放的金币奖励
        :param number: 要最多选出number个用户发奖励
        :param userIds: 要从userIds中最多选择number个用户出来。 useIds会被修改, 删除了发送过奖励的用户
        :param excludeUserId: 要排除的userId, 这个id不给发奖励
        :return: 发送过奖励的用户的set
        '''

        toUserIds = {}  # 待发奖的用户
        while len(userIds) > 0 and number > 0:

            # 随机选择一个userId
            i = random.randint(0, len(userIds) - 1)
            userId = userIds[i]

            # 排除掉我们欲排除的userId
            if userId == excludeUserId:
                del userIds[i]
                continue

            # 这是我们待发奖的用户
            toUserIds[userId] = rewardChip
            del userIds[i]
            number -= 1

        conf = carsconf.getFireConf()
        for userId in toUserIds.iterkeys():
            Sender.sendFireRewardMsg(userId, fireId, conf['timeout'], name, fireIndex)

        return toUserIds    

    @classmethod
    @locked
    def _genFireId(cls):
        '''自增礼花ID'''

        cls.fireId += 1
        return cls.fireId

    @classmethod
    @locked
    def _saveFireRewardsInfo(cls, fireId, isSys, fireIndex, userName, userIdRewards):
        '''保存礼花奖励信息'''

        cls.fires[fireId] = {'type': isSys, 'fireIndex': fireIndex, 'userName': userName, 'users': userIdRewards}

    @classmethod
    @locked
    def _checkAndDel(cls, fireId, userId):
        '''检查返回用户的礼花奖励，并且删除该用户'''

        if fireId not in cls.fires:
            return 0, False, 0, ''

        fireRewardsInfo = cls.fires[fireId]['users']
        if userId not in fireRewardsInfo:
            return 0, False, 0, ''

        reward = fireRewardsInfo[userId]
        del fireRewardsInfo[userId]
        return reward, cls.fires[fireId]['type'], cls.fires[fireId]['fireIndex'], cls.fires[fireId]['userName']

    @classmethod
    @locked
    def _delFireRewardsInfo(cls, fireId):
        '''删除礼花奖励信息'''

        cls.fires.pop(fireId, None)

    @classmethod
    def _timeoutDelFireRewardsInfo(cls, fireId):
        '''超时到了，触发删除礼花奖励等信息'''

        cls._delFireRewardsInfo(fireId)

    def _sysFireLoop(self):
        '''系统礼花协程'''

        tasklet = stackless.getcurrent()._fttask

        while True:
            # 读取配置
            sysConf = carsconf.getFireConf().get('system', {})
            beginStr = sysConf.get('begin', '2016-06-03 12:00:00')
            endStr = sysConf.get('end', '2016-06-03 12:00:00')

            begin = time.mktime(time.strptime(beginStr, '%Y-%m-%d %H:%M:%S'))
            end = time.mktime(time.strptime(endStr, '%Y-%m-%d %H:%M:%S'))

            now = int(time.time())
            if now < begin or now >= end:
                tasklet.sleepNb(5)  # 每5秒转一次
                continue

            # 下一个整点时刻
            nextHourBegin = now + const.ONE_HOUR_SEC - now % const.ONE_HOUR_SEC

            # 1小时为基本单位, 下面执行在这个1小时内的逻辑
            nums = sysConf.get('times_per_hour', 0)  # 要放的礼花次数
            leastInterval = sysConf.get('least_interval', 0)  # 发放时间最小间隔

            # 到下一个整点时刻不到半小时, 则放弃
            if nextHourBegin - now < const.ONE_HOUR_SEC / 2:
                tasklet.sleepNb(5)  # 每5秒转一次
                continue

            sendTimes = set()  # 本小时内发放过的时间点
            while len(sendTimes) < nums:
                # nextHourBegin - 10是避免万一这把选择的时间点跟下一个小时内选择的第一个时间点很近,导致前端动画显示问题
                selectedOneTime = random.randint(now, nextHourBegin - 10)

                # 检查选出来的t是否足够间隔. 不够间隔,则要重新选一个
                for t in sendTimes:
                    if abs(t - selectedOneTime) < leastInterval:
                        continue

                sendTimes.add(selectedOneTime)

            # 转换类型为数组, 方便排序
            sendTimes = [t for t in sendTimes]
            sendTimes.sort()

            sendTimesStrs = []
            for t in sendTimes:
                sendTimesStrs.append(time.strftime('%H:%M:%S', time.localtime(t)))
            ftlog.info('_sysFireLoop, for current hour, sys fire at ', sendTimesStrs)

            # 在各个时间点, 系统发放礼花
            for t in sendTimes:
                now = int(time.time())
                tasklet.sleepNb(max(t - now, 0))

                self._table.doTableCall(MsgPack(), 0, 0, 'sys_fruit_fire', '')

            # 等到下一个整点
            now = int(time.time())
            tasklet.sleepNb(max(nextHourBegin - now, 0))
