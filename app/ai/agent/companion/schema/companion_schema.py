from pydantic import BaseModel, Field


class EmotionSchema(BaseModel):
    """情感分析的结构化输出"""
    emotion: str = Field(description="情绪标签，只能从：快乐/平静/难过/焦虑/愤怒/孤独/委屈/兴奋/害怕/疲惫/迷茫/惊喜 中选一个")
    intensity: int = Field(description="情绪强度1-10", ge=1, le=10)
    is_crisis: bool = Field(description="用户是否流露自伤/自杀倾向")


class MemoryItemSchema(BaseModel):
    """单条长期记忆"""
    content: str = Field(description="一句话记忆内容，简洁客观")
    category: str = Field(description="记忆类别：fact/preference/relationship/event/goal/emotion")
    importance: float = Field(description="重要性0-1", ge=0, le=1)


class MemoryListSchema(BaseModel):
    """长期记忆提取的结构化输出"""
    memories: list[MemoryItemSchema] = Field(default_factory=list, description="提取到的记忆列表，无则空")


class ProfileSchema(BaseModel):
    """用户画像的结构化输出"""
    name: str | None = Field(default=None, description="用户姓名，对话中没提则为null")
    occupation: str | None = Field(default=None, description="职业/学业，没提则为null")
    preferences: list[str] = Field(default_factory=list, description="喜好列表，如爬山/撸猫")
    relationships: list[str] = Field(default_factory=list, description="重要的人际关系，如养了一只叫团子的猫")


class MusicPickSchema(BaseModel):
    """音乐选曲的结构化输出（阶段五）"""
    file: str = Field(description="选中的音乐文件名，必须原样来自候选列表的 file 字段，不能编造")
    reason: str = Field(description="一句话推荐理由，温柔自然，30字以内，不出现技术词")


class WorkingMemorySchema(BaseModel):
    """工作记忆更新的结构化输出"""
    summary: str = Field(description="对用户当前状态的整体了解，100字以内，第三人称")
    open_topics: list[str] = Field(default_factory=list, description="值得后续跟进关心的话题，最多5个，没有则空")
    current_emotion: str = Field(description="用户当前的整体情绪状态，一个词")
