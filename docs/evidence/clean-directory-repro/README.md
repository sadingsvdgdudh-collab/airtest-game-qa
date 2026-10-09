# 新目录与新Python环境复现

公开项目复制至独立工作目录，建立未继承系统site-packages的Python3.12虚拟环境，安装40项固定依赖并重新编译协议桥。[安装记录](installation.json)、[版本记录](versions.json)、[依赖核查](post-fix-verification.json)、[自检日志](post-fix-offline-tests.log)和[32个收集ID](post-fix-collected-ids.json)分别对应安装、自检和收集，不代表32条实跑。

修正后28项框架自检通过，真实购买/任务2ID各五轮通过，另购买API单例通过：[完成记录](completion.json)、[UI五轮](../stendhal-ui-batch2-final/index.html)、[API单例](../clean-directory-api/index.html)。UI的91份公开执行源与原项目一致，冻结早于正式首例；不包含安装生成的6份egg-info。

安装/准备JSON中的zero-live、pending字段是开始执行前的历史状态；实际完成状态以completion.json和真实报告为准。复用本机Java、原版游戏服务、SDK/Android模拟器，不声称全新机器或重新安装全部游戏环境验收。
