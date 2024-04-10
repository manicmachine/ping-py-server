# FLASK CONFIGURATION FILE
import os


class Config(object):
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI=f'sqlite:///{os.path.join('../instance/', 'ping.sqlite')}'

class ProductionConfig(Config):
    SECRET_KEY='change-me'

class DevelopmentConfig(Config):
    DEBUG = True,
    SECRET_KEY='dev'

class TestingConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True