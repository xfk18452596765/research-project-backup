# DayXX：任务名称

## 一、任务定位

说明本日承接哪一天、解决什么问题，以及在整体技术路线中的位置。

## 二、今日目标

列出本日计划完成的核心机制和事件链。

## 三、已完成内容

测试和实验完成后，根据实际代码逐项填写，不保留“待填写”。

## 四、核心流程或公式

给出事件链、状态转移、关键参数或指标定义。

## 五、目录说明

```text
DayXX_任务名称/
├─ code/
├─ docs/
├─ figures/
├─ logs/
├─ results/
└─ README.md
```

列出当天实际新增的主要文件及其职责。

## 六、运行方法

至少包含：

```powershell
# 当天自动测试
python ".\daily\DayXX_任务名称\code\test_xxx.py"

# 完整回归测试
python ".\daily\DayXX_任务名称\code\run_day03_dayXX_regression.py"

# 主程序或实验
python ".\daily\DayXX_任务名称\code\main_xxx.py"
```

只写实际存在的命令。

## 七、测试结果

填写真实终端输出，例如：

```text
All DayXX ... tests passed.
All Day03-DayXX regression tests passed.
```

不得在没有实际运行时写“测试已通过”。

## 八、关键实验结果

填写实际生成的结果、关键数值和最终状态。

## 九、结果文件

列出`logs/`和`results/`中的实际文件。

## 十、当前实现边界

明确本日没有实现的内容，避免后续误认为已经完成。

## 十一、今日结论

总结本日解决的问题，以及该成果对下一阶段的作用。

## 十二、明日衔接

说明下一天只做什么、不提前做什么。

---

## 每日固定收尾顺序

1. 运行当天自动测试；
2. 运行Day03到当天的完整回归测试；
3. 运行当天主程序或实验；
4. 检查`logs/`和`results/`输出；
5. 根据真实结果补全本目录`README.md`；
6. 检查README中没有“待填写”；
7. 再执行`git add`、`git commit`和Pull Request。
