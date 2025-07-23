#! -*- coding:utf-8 -*-
# Author:   qianyong
# Created:  2016.06.28 21.54


from freetime.entity.msg import MsgPack
from freetime.util import log as ftlog
from hall.entity import hallvip

from cars.entity import carsconf
from cars.entity import const
from cars.entity.util import UtilFunc
from cars.gametable.carssender import Sender

import random
import time


class Chat(object):
    '''聊天功能'''

    def __init__(self, table):
        self._table = table
        '''@type: cars.gametable.carstable.CarsTable'''

        # 10秒后启动系统预置消息的检测播放
        UtilFunc.callLater(10, self._broadcastDefineSysMsgTimer)

    def userChat(self, userId, chatType, msg):
        '''玩家发送的聊天消息'''

        now = time.time()
        chatConf = carsconf.getChatConf()
        vipRequired = chatConf.get('vip_required', 0)
        interval = chatConf.get('interval_chat', 0)
        definedChats = chatConf.get('define_chat', [])
        guixiePeriod = chatConf.get('period_after_guixie', 0)

        # 时间间隔限制
        user = self._table.users[userId]
        if now - user.lastChatAt < interval:
            msg = const.CHAT_INTERVAL_LIMIT
            return self.sendSysChatToUser(msg, const.CHAT_LABLE_NOMAL_TYPE, userId)

        # 跪谢以外的消息都需要vip等级限制
        vipInfo = hallvip.userVipSystem.getUserVip(userId)
        vipLevel = vipInfo.vipLevel.level
        if msg != self._table.fire.guixie:
            if vipLevel < vipRequired:
                msg = const.CHAT_VIP_LIMIT_FMT.format(vipLevel=carsconf.getChatConf().get('vip_required', 0))
                return self.sendSysChatToUser(msg, const.CHAT_LABLE_NOMAL_TYPE, userId)

        # 跪谢消息, 礼花超过1分钟以后不让发
        if msg == self._table.fire.guixie and now - self._table.fire.fireAt > guixiePeriod:
            return

        # 不能发送自定义消息
        if chatType != const.CHAT_TYPE_EMOTION and msg not in definedChats and msg != self._table.fire.guixie:
            ftlog.warn('userChat', userId, 'is sending a custom msg:', chatType, msg)
            return

        user.lastChatAt = now
        ftlog.info('userChat', userId, chatType, msg)

        # 构建并广播消息给所有人
        userName = UtilFunc.getUserName(userId)
        mo = Sender.buildChatMsg(userId, userName, vipLevel, chatType, msg, const.CHAT_LABLE_NOMAL_TYPE)
        for userId_ in self._table.users:
            Sender.directlySendMsg(userId_, mo)

    def broadcastSysChat(self, msg, lableType):
        '''系统发的聊天消息广播给所有人'''

        mo = Sender.buildChatMsg(const.CHAT_SYS_USER_ID, const.CHAT_SYS_USER_NAME,
                                 const.CHAT_SYS_VIP_LEVEL, const.CHAT_TYPE_TEXT, msg, lableType)

        for userId in self._table.users:
            Sender.directlySendMsg(userId, mo)

    def sendSysChatToUser(self, msg, lableType, toUserId):
        '''系统发聊天消息给某个人'''

        mo = Sender.buildChatMsg(const.CHAT_SYS_USER_ID, const.CHAT_SYS_USER_NAME,
                                 const.CHAT_SYS_VIP_LEVEL, const.CHAT_TYPE_TEXT, msg, lableType)
        Sender.directlySendMsg(toUserId, mo)

    def _broadcastDefineSysMsgTimer(self):
        '''周期性的发送系统预置消息'''

        chatConf = carsconf.getChatConf()
        period = chatConf.get('period_sysmsg', 600)  # 预置系统消息的发送间隔
        msgs = chatConf.get('game_define_sysmsg', [])
        if len(msgs) > 0:
            msg = random.choice(msgs)

            mo = MsgPack()
            mo.setParam('text', msg)
            self._table.doTableCall(mo, 0, 0, 'sys_chat_define_msg', '')

        # 周期性的再次在period时间之后启动自己
        UtilFunc.callLater(period, self._broadcastDefineSysMsgTimer)
