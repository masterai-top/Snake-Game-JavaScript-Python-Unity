#! -*- coding:utf-8 -*-
# Author:   qianyong
# Created:  2016.07.13 17:58

from poker.entity.configure import gdata
from poker.entity.dao import userdata, gamedata, tabledata

from cars.entity import const
from cars.entity.util import UtilFunc
from cars.gametable.carssender import Sender

import time


class Debug(object):
    '''debug测试用到的相关, 为保证安全, 这些函数仅能在测试环境生效!'''

    @classmethod
    def doDebug(cls, msg):
        '''执行debug命令'''

        # debug命令仅在测试环境有效
        if not gdata.enableTestHtml():
            return

        userId = msg.getParam('userId')
        action = msg.getParam('action1')  # action已被占用,使用ation1

        if action == 'set_userdata':
            key = msg.getParam('key')
            value = msg.getParam('value')
            return cls.__setUserData(userId, key, value)

        elif action == 'get_userdata':
            key = msg.getParam('key')
            return cls.__getUserData(userId, key)

        elif action == 'set_gamedata':
            key = msg.getParam('key')
            value = msg.getParam('value')
            return cls.__setGameData(userId, key, value)

        elif action == 'get_gamedata':
            key = msg.getParam('key')
            return cls.__getUserData(userId, key)

        elif action == 'set_tabledata':
            key = msg.getParam('key')
            value = msg.getParam('value')
            return cls.__setTableData(userId, key, value)

        elif action == 'get_tabledata':
            key = msg.getParam('key')
            return cls.__getTableData(userId, key)

        elif action == 'set_daydata':
            data = msg.getParam('data')
            return cls.__setDayData(userId, data)

        elif action == 'get_daydata':
            return cls.__getDayData(userId)

    @classmethod
    def __setUserData(cls, userId, key, value):
        '''设置用户数据'''

        userdata.setAttr(userId, key, value)
        Sender.sendDebugMsg(userId, 'set_userdata', 1)

    @classmethod
    def __getUserData(cls, userId, key):
        '''获取用户数据'''

        value = userdata.getAttr(userId, key)
        Sender.sendDebugMsg(userId, 'get_userdata', value)

    @classmethod
    def __setGameData(cls, userId, key, value):
        '''设置用户的游戏数据'''

        gamedata.setGameAttr(userId, const.GAME_ID, key, value)
        Sender.sendDebugMsg(userId, 'set_gamedata', 1)

    @classmethod
    def __getGameData(cls, userId, key):
        '''获取用户的游戏数据'''

        value = gamedata.getGameAttr(userId, const.GAME_ID, key)
        Sender.sendDebugMsg(userId, 'get_gamedata', value)

    @classmethod
    def __setTableData(cls, userId, key, value):
        '''设置牌桌数据'''

        tabledata.setTableAttr(const.ROOM_ID, const.FAKE_TABLE_ID, key, value)
        Sender.sendDebugMsg(userId, 'set_tabledata', 1)

    @classmethod
    def __getTableData(cls, userId, key):
        '''获取牌桌数据'''

        value = tabledata.getTableAttr(const.ROOM_ID, const.FAKE_TABLE_ID, key)
        Sender.sendDebugMsg(userId, 'get_tabledata', value)

    @classmethod
    def __setDayData(cls, userId, data):
        '''设置每日数据'''

        date = time.strftime("%Y%m%d", time.localtime())
        UtilFunc.setDayData(userId, data, date)
        Sender.sendDebugMsg(userId, 'set_daydata', 1)

    @classmethod
    def __getDayData(cls, userId):
        '''获取每日数据'''

        date = time.strftime("%Y%m%d", time.localtime())
        data = UtilFunc.getDayData(userId, date)
        Sender.sendDebugMsg(userId, 'get_daydata', data)
