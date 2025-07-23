#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库连接管理模块
负责数据库连接池的创建、管理和维护
"""

import os
import sys
from contextlib import contextmanager
from threading import Thread
import logging

# 动态导入数据库驱动
try:
    import mysql.connector
    from mysql.connector.pooling import MySQLConnectionPool
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False

try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False


class SimpleConnectionPool:
    """简单的SQL Server连接池实现"""
    
    def __init__(self, max_connections, connection_creator):
        self.max_connections = max_connections
        self.connection_creator = connection_creator
        self.connections = []
        self.in_use = set()
        self.logger = logging.getLogger(__name__)
    
    def get_connection(self):
        """获取数据库连接"""
        # 清理无效引用
        self.in_use = {conn for conn in self.in_use if conn in self.connections}
        
        # 尝试复用现有连接
        for i in range(len(self.connections) - 1, -1, -1):
            conn = self.connections[i]
            if conn not in self.in_use:
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.close()
                    self.in_use.add(conn)
                    return conn
                except Exception as e:
                    self.logger.warning(f"连接池中的连接已失效: {e}")
                    try:
                        self.connections.pop(i)
                    except:
                        pass
        
        # 创建新连接
        if len(self.connections) < self.max_connections:
            try:
                conn = self.connection_creator()
                self.connections.append(conn)
                self.in_use.add(conn)
                return conn
            except Exception as e:
                self.logger.error(f"创建新连接失败: {e}")
                raise
        
        raise Exception("连接池已满，无法获取新连接")
    
    def release(self, connection):
        """释放连接"""
        if connection in self.in_use:
            self.in_use.remove(connection)
            self.logger.debug(f"连接已释放，当前使用中: {len(self.in_use)}/{len(self.connections)}")
    
    def close_all(self):
        """关闭所有连接"""
        for conn in self.connections:
            try:
                conn.close()
            except Exception as e:
                self.logger.warning(f"关闭连接时出错: {e}")
        self.connections = []
        self.in_use = set()
        self.logger.info("所有数据库连接已关闭")


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, config):
        self.config = config
        self.primary_pool = None
        self.training_pools = {}
        self.logger = logging.getLogger(__name__)
        
        # 数据库类型检测
        self.db_type = self._detect_db_type()
        
    def _detect_db_type(self):
        """检测数据库类型"""
        primary_config = self.config.get('primary_connection', {})
        driver = primary_config.get('driver', '')
        
        if 'mysql' in driver.lower() or 'MySQL' in driver:
            return 'mysql'
        elif 'sql server' in driver.lower() or 'ODBC' in driver:
            return 'sqlserver'
        else:
            return 'unknown'
    
    def init_connection_pools(self):
        """初始化连接池"""
        try:
            # 初始化主连接池
            self._init_primary_pool()
            
            # 初始化训练连接池
            self._init_training_pools()
            
            self.logger.info("数据库连接池初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"连接池初始化失败: {e}")
            return False
    
    def _init_primary_pool(self):
        """初始化主连接池"""
        primary_config = self.config.get('primary_connection', {})
        
        self.logger.debug(f"DatabaseManager配置: {self.config}")
        self.logger.debug(f"主连接配置: {primary_config}")
        
        if not primary_config:
            raise ValueError("主数据库连接配置不能为空")
        
        def create_connection():
            return self._create_connection(primary_config)
        
        self.primary_pool = SimpleConnectionPool(
            max_connections=10,
            connection_creator=create_connection
        )
        
        self.logger.info("主数据库连接池初始化完成")
    
    def _init_training_pools(self):
        """初始化训练连接池"""
        training_configs = self.config.get('training_connections', [])
        
        for config in training_configs:
            name = config.get('name', 'unknown')
            
            def create_connection():
                return self._create_connection(config)
            
            self.training_pools[name] = SimpleConnectionPool(
                max_connections=5,
                connection_creator=create_connection
            )
        
        self.logger.info(f"训练连接池初始化完成: {list(self.training_pools.keys())}")
    
    def _create_connection(self, config):
        """创建数据库连接"""
        if self.db_type == 'mysql':
            return self._create_mysql_connection(config)
        elif self.db_type == 'sqlserver':
            return self._create_sqlserver_connection(config)
        else:
            raise ValueError(f"不支持的数据库类型: {self.db_type}")
    
    def _create_mysql_connection(self, config):
        """创建MySQL连接"""
        if not MYSQL_AVAILABLE:
            raise ImportError("MySQL驱动未安装")
        
        return mysql.connector.connect(
            host=config.get('host', config.get('server')),
            port=config.get('port', 3306),
            user=config.get('user', config.get('uid')),
            password=config.get('password', config.get('pwd')),
            database=config.get('database', config.get('dbname')),
            charset='utf8mb4',
            autocommit=True
        )
    
    def _create_sqlserver_connection(self, config):
        """创建SQL Server连接"""
        if not PYODBC_AVAILABLE:
            raise ImportError("PYODBC驱动未安装")
        
        driver = config.get('driver', '{ODBC Driver 18 for SQL Server}')
        server = config.get('server', 'localhost')
        port = config.get('port', 1433)
        database = config.get('database', config.get('dbname'))
        uid = config.get('uid', config.get('user'))
        pwd = config.get('pwd', config.get('password'))
        
        # 构建连接字符串
        conn_str = f"DRIVER={driver};SERVER={server},{port};DATABASE={database};UID={uid};PWD={pwd};TrustServerCertificate=yes;"
        
        return pyodbc.connect(conn_str)
    
    @contextmanager
    def get_connection(self, pool_name='primary'):
        """获取数据库连接的上下文管理器"""
        self.logger.debug(f"获取连接池: {pool_name}")
        self.logger.debug(f"可用连接池: primary={self.primary_pool is not None}, training={list(self.training_pools.keys())}")
        
        if pool_name == 'primary':
            pool = self.primary_pool
        else:
            pool = self.training_pools.get(pool_name)
        
        if not pool:
            raise ValueError(f"未找到连接池: {pool_name}")
        
        connection = None
        try:
            connection = pool.get_connection()
            yield connection
        finally:
            if connection:
                pool.release(connection)
    
    @contextmanager
    def get_cursor(self, pool_name='primary'):
        """获取数据库游标的上下文管理器 - 从示例代码移植"""
        with self.get_connection(pool_name) as connection:
            cursor = None
            try:
                cursor = connection.cursor()
                yield cursor
                connection.commit()  # 提交事务
            except Exception as e:
                try:
                    connection.rollback()  # 回滚事务
                except:
                    pass
                raise e
            finally:
                if cursor:
                    try:
                        cursor.close()
                    except:
                        pass
    
    def get_primary_config(self):
        """获取主数据库配置"""
        return self.config.get('primary_connection', {})
    
    def get_database_info(self):
        """获取数据库信息"""
        return {
            'type': self.db_type,
            'primary_config': self.get_primary_config(),
            'training_pools': list(self.training_pools.keys()),
            'mysql_available': MYSQL_AVAILABLE,
            'pyodbc_available': PYODBC_AVAILABLE
        }
    
    def close_all_connections(self):
        """关闭所有连接"""
        if self.primary_pool:
            self.primary_pool.close_all()
        
        for pool in self.training_pools.values():
            pool.close_all()
        
        self.logger.info("所有数据库连接已关闭")


# 单例模式
_db_manager = None

def get_database_manager(config=None):
    """获取数据库管理器单例"""
    global _db_manager
    if _db_manager is None and config:
        _db_manager = DatabaseManager(config)
    return _db_manager


def init_database_manager(config):
    """初始化数据库管理器"""
    global _db_manager
    _db_manager = DatabaseManager(config)
    return _db_manager.init_connection_pools()


if __name__ == "__main__":
    # 测试代码
    test_config = {
        'primary_connection': {
            'driver': '{ODBC Driver 18 for SQL Server}',
            'server': '10.10.10.135',
            'database': 'gd_suncere_product_data_air',
            'uid': 'Develop',
            'pwd': 'Dev@996996',
            'port': 1433
        }
    }
    
    manager = DatabaseManager(test_config)
    print(f"数据库信息: {manager.get_database_info()}")