#! -*- coding:utf-8 -*-
# Author:   qianyong
# Created:  2016.06.24 20.53

import freetime.util.log as ftlog
from poker.entity.configure import gdata
from poker.protocol import runcmd
from poker.protocol.decorator import markCmdActionHandler, markCmdActionMethod
from hall.servers.common.base_checker import BaseMsgPackChecker


@markCmdActionHandler
class RoomTcpHandler(BaseMsgPackChecker):
    @markCmdActionMethod(cmd='room', action="quick_start", clientIdVer=0, scope='game')
    def doRoomQuickStart(self, roomId, userId):
        msg = runcmd.getMsgPack()
        ftlog.debug('msg=', msg, caller=self)
        gdata.rooms()[roomId].doQuickStart(msg)

    @markCmdActionMethod(cmd='room', action="leave", clientIdVer=0, scope='game')
    def doRoomLeave(self, roomId, userId):
        msg = runcmd.getMsgPack()
        gdata.rooms()[roomId].doLeave(userId, msg)
