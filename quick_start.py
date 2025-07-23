# coding=UTF-8
'''
quickstart模块
'''

from poker.entity.game.quick_start import BaseQuickStart, \
    BaseQuickStartDispatcher
from poker.entity.game.rooms.room import TYRoom
from hall.entity.todotask import TodoTaskShowInfo, TodoTaskHelper,\
    TodoTaskOrderShow
import freetime.util.log as ftlog
from freetime.entity.msg import MsgPack
from poker.protocol import router
from poker.util import strutil

from cars.entity import const
from cars.entity.util import UtilFunc
from cars.entity import carsconf

class CarsQuickStartDispatcher(BaseQuickStartDispatcher):
    '''
    按clientId分发快速开始请求
    '''
    @classmethod
    def dispatchQuickStart(cls, msg, userId, gameId, roomId, tableId, playMode, clientId):
        return CarsQuickStartV4_0.onCmdQuickStart(msg, userId, gameId, roomId, tableId, playMode, clientId)


class CarsQuickStartV4_0(BaseQuickStart):

    @classmethod
    def _chooseRoom(cls, userId, gameId, playMode):
        return super(CarsQuickStartV4_0, cls)._chooseRoom(userId, gameId, playMode)


    @classmethod
    def _sendTodoTaskToUser(cls, userId, errorCode):
        tip = 'system exception, please try again ! code=' + str(errorCode)
        t = TodoTaskShowInfo(tip, True)
        msg = TodoTaskHelper.makeTodoTaskMsg(const.GAME_ID, userId, t)
        router.sendToUser(msg, userId)

    @classmethod
    def _onEnterRoomFailed(cls, msg, checkResult, userId, clientId, roomId=0):
        ftlog.debug('clownQuickStartV4_0._onEnterRoomFailed userId=', userId, 'roomId=', roomId, 'checkResult=', checkResult)
        if checkResult == TYRoom.ENTER_ROOM_REASON_LESS_MIN :
            mo = MsgPack()
            mo.setCmd('quick_start')
            mo.setResult('gameId', const.GAME_ID)
            mo.setResult('isOK', False)
            mo.setResult('reason', TYRoom.ENTER_ROOM_REASON_LESS_MIN) 
            products = UtilFunc.getProductsGroup(userId, clientId, carsconf.getProductsConf())
            mo.setResult('products', products) 
            router.sendToUser(mo, userId)
        elif checkResult == TYRoom.ENTER_ROOM_REASON_CONFLICT :
            cls._sendTodoTaskToUser(userId, checkResult)
        elif checkResult == TYRoom.ENTER_ROOM_REASON_INNER_ERROR :
            cls._sendTodoTaskToUser(userId, checkResult)
        elif checkResult == TYRoom.ENTER_ROOM_REASON_ROOM_FULL :
            cls._sendTodoTaskToUser(userId, checkResult)
        elif checkResult == TYRoom.ENTER_ROOM_REASON_GREATER_MAX :
            cls._sendTodoTaskToUser(userId, checkResult)
        else:  # TYRoom.ENTER_ROOM_REASON_INNER_ERROR :
            cls._sendTodoTaskToUser(userId, TYRoom.ENTER_ROOM_REASON_INNER_ERROR)


    @classmethod
    def _getCandidateRoomIds(cls, gameId, playMode):
        return super(CarsQuickStartV4_0, cls)._getCandidateRoomIds(gameId, playMode)


    @classmethod
    def _canQuickEnterRoom(cls, userId, gameId, roomId, isOnly):
        return super(CarsQuickStartV4_0, cls)._canQuickEnterRoom(userId, gameId, roomId, isOnly)