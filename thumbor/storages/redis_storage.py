#!/usr/bin/python
# -*- coding: utf-8 -*-

# thumbor imaging service
# https://github.com/globocom/thumbor/wiki

# Licensed under the MIT license:
# http://www.opensource.org/licenses/mit-license
# Copyright (c) 2011 globo.com timehome@corp.globo.com

import logging

from json import loads, dumps
from datetime import datetime, timedelta

from redis import Redis, RedisError

from thumbor.storages import BaseStorage
from thumbor.utils import on_exception

logger = logging.getLogger('thumbor')


class Storage(BaseStorage):

    storage = None

    def __init__(self, context):
        BaseStorage.__init__(self, context)
        self.storage = self.reconnect_redis()

    def reconnect_redis(self):
        if not Storage.storage:
            Storage.storage = Redis(
                port=self.context.config.REDIS_STORAGE_SERVER_PORT,
                host=self.context.config.REDIS_STORAGE_SERVER_HOST,
                db=self.context.config.REDIS_STORAGE_SERVER_DB,
                password=self.context.config.REDIS_STORAGE_SERVER_PASSWORD
            )

        return Storage.storage

    def on_redis_error(self, fname, exc_type, exc_value):
        '''Callback executed when there is a redis error.

        :param string fname: Function name that was being called.
        :param type exc_type: Exception type
        :param Exception exc_value: The current exception
        :returns: Default value or raise the current exception
        '''

        Storage.storage = None

        if self.context.config.REDIS_STORAGE_IGNORE_ERRORS is True:
            # Based on no_storage
            return_map = {
                'exists': False,
                'put': '',
                'put_crypto': '',
                'put_detector_path': '',
            }

            logger.warning("Redis storage failure: %s" % exc_value)

            return return_map.get(fname, None)
        else:
            raise exc_value

    def __key_for(self, url):
        return 'thumbor-crypto-%s' % url

    def __detector_key_for(self, url):
        return 'thumbor-detector-%s' % url

    @on_exception(on_redis_error, RedisError)
    def put(self, path, bytes):
        self.storage.set(path, bytes)
        self.storage.expireat(
            path, datetime.now() + timedelta(
                seconds=self.context.config.STORAGE_EXPIRATION_SECONDS
            )
        )
        return path

    @on_exception(on_redis_error, RedisError)
    def put_crypto(self, path):
        if not self.context.config.STORES_CRYPTO_KEY_FOR_EACH_IMAGE:
            return

        if not self.context.server.security_key:
            raise RuntimeError(
                "STORES_CRYPTO_KEY_FOR_EACH_IMAGE can't be True if no "
                "SECURITY_KEY specified"
            )

        key = self.__key_for(path)
        self.storage.set(key, self.context.server.security_key)
        return key

    @on_exception(on_redis_error, RedisError)
    def put_detector_data(self, path, data):
        key = self.__detector_key_for(path)
        self.storage.set(key, dumps(data))
        return key

    @on_exception(on_redis_error, RedisError)
    def get_crypto(self, path):
        if not self.context.config.STORES_CRYPTO_KEY_FOR_EACH_IMAGE:
            return None

        crypto = self.storage.get(self.__key_for(path))

        if not crypto:
            return None
        return crypto

    @on_exception(on_redis_error, RedisError)
    def get_detector_data(self, path):
        data = self.storage.get(self.__detector_key_for(path))

        if not data:
            return None
        return loads(data)

    @on_exception(on_redis_error, RedisError)
    def exists(self, path):
        return self.storage.exists(path)

    @on_exception(on_redis_error, RedisError)
    def remove(self, path):
        if not self.exists(path):
            return
        return self.storage.delete(path)

    @on_exception(on_redis_error, RedisError)
    def get(self, path):
        return self.storage.get(path)
