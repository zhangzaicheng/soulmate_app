-- ============================================
-- AI情感陪伴系统 soulmate_db 建库建表脚本
-- MySQL 5.7+ / 8.0
-- ============================================
CREATE DATABASE IF NOT EXISTS soulmate_db DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE soulmate_db;

-- 用户表（JWT 登录体系）
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE COMMENT '登录名',
    password_hash VARCHAR(100) NOT NULL COMMENT 'bcrypt哈希',
    nickname      VARCHAR(50)  DEFAULT NULL COMMENT '昵称',
    email         VARCHAR(100) DEFAULT NULL UNIQUE COMMENT '邮箱，用于验证码找回密码',
    avatar        VARCHAR(255) DEFAULT NULL COMMENT '头像地址',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_username (username)
) ENGINE=InnoDB COMMENT='用户表';

-- 会话表（业务持久化以MySQL为准，Redis只做注册缓存/锁）
CREATE TABLE IF NOT EXISTS conversations (
    session_id VARCHAR(64) PRIMARY KEY COMMENT 'uuid hex',
    user_id    INT          NOT NULL,
    title      VARCHAR(100) DEFAULT '新的对话',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_user (user_id)
) ENGINE=InnoDB COMMENT='会话表';

-- 消息留档表（完整对话历史，前端回显从这里读）
CREATE TABLE IF NOT EXISTS messages (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    role       VARCHAR(10)  NOT NULL COMMENT 'user/assistant',
    content    MEDIUMTEXT,
    emotion    VARCHAR(20)  DEFAULT NULL COMMENT 'assistant回复时识别到的用户情绪',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_session (session_id)
) ENGINE=InnoDB COMMENT='消息表';

-- 情绪记录表（情感曲线可视化）
CREATE TABLE IF NOT EXISTS emotion_records (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    emotion    VARCHAR(20) NOT NULL COMMENT '12类情绪标签',
    intensity  INT DEFAULT 5 COMMENT '1-10',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_user (user_id)
) ENGINE=InnoDB COMMENT='情绪记录表';

-- ============ 以下表阶段二（完整记忆系统）使用 ============

-- 长期记忆元数据表（向量本体存Chroma，以memory_id关联）
CREATE TABLE IF NOT EXISTS long_term_memories (
    memory_id     VARCHAR(64) PRIMARY KEY COMMENT '与Chroma中的id一致',
    user_id       INT NOT NULL,
    content       TEXT NOT NULL COMMENT '记忆内容',
    category      VARCHAR(20) DEFAULT 'fact' COMMENT 'fact/emotion/relationship/event/preference/goal/concern',
    emotion       VARCHAR(20) DEFAULT NULL,
    importance    DECIMAL(3,2) DEFAULT 0.5 COMMENT '0-1重要性',
    layer         TINYINT DEFAULT 3 COMMENT '1核心/2重要/3常规',
    access_count  INT DEFAULT 0,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_user (user_id)
) ENGINE=InnoDB COMMENT='长期记忆元数据表';

-- 用户档案表
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id      INT PRIMARY KEY,
    name         VARCHAR(50)  DEFAULT NULL,
    occupation   VARCHAR(50)  DEFAULT NULL,
    preferences  JSON DEFAULT NULL COMMENT '喜好标签列表',
    relationships JSON DEFAULT NULL COMMENT '重要的人/关系',
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB COMMENT='用户档案表';

-- 工作记忆表（跨会话的整体了解，始终注入prompt）
CREATE TABLE IF NOT EXISTS working_memory (
    user_id        INT PRIMARY KEY,
    summary        VARCHAR(500) DEFAULT NULL COMMENT '对用户的整体了解，200字内',
    open_topics    JSON DEFAULT NULL COMMENT '待跟进的话题，最多5个',
    current_emotion VARCHAR(20) DEFAULT NULL,
    updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB COMMENT='工作记忆表';

-- ============ 阶段四：主动关心 / 纪念日提醒 ============

-- 主动消息表（AI主动关心/纪念日提醒，前端轮询拉取）
CREATE TABLE IF NOT EXISTS proactive_messages (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    kind       VARCHAR(20) DEFAULT 'care' COMMENT 'care=主动关心, memorial=纪念日提醒',
    content    TEXT NOT NULL,
    is_read    TINYINT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_user (user_id)
) ENGINE=InnoDB COMMENT='AI主动消息表';

-- 纪念日表
CREATE TABLE IF NOT EXISTS memorial_days (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL,
    title         VARCHAR(100) NOT NULL COMMENT '纪念日名称',
    date_str      VARCHAR(10) NOT NULL COMMENT 'MM-DD(每年重复) 或 YYYY-MM-DD(单次)',
    repeat_yearly TINYINT DEFAULT 1,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_user (user_id)
) ENGINE=InnoDB COMMENT='纪念日表';
