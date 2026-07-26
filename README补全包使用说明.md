# README补全包使用说明

## 一、包含内容

本补全包包含以下已完成任务的顶层`README.md`：

```text
daily/
├─ Day03_仿真架构与事件设计/README.md
├─ Day04_DCF基础框架/README.md
├─ Day05_DCF信道忙与退避冻结/README.md
├─ Day06_DCF碰撞与重传/README.md
├─ Day07_DCF指标采集/README.md
└─ Day08_DCF验证与调试/README.md
```

## 二、推荐替换方式

将压缩包解压到：

```text
C:\research-project-backup-main\
```

当系统询问是否覆盖时，选择覆盖对应的`README.md`。

压缩包内已经保留`daily/DayXX_任务名称/README.md`路径，因此不需要逐个移动文件。

## 三、替换后检查

在项目根目录执行：

```powershell
Get-ChildItem ".\daily\Day0*\README.md"
```

查看其中一个文件：

```powershell
Get-Content ".\daily\Day08_DCF验证与调试\README.md"
```

## 四、提交建议

```powershell
git add ".\daily\Day03_仿真架构与事件设计\README.md"
git add ".\daily\Day04_DCF基础框架\README.md"
git add ".\daily\Day05_DCF信道忙与退避冻结\README.md"
git add ".\daily\Day06_DCF碰撞与重传\README.md"
git add ".\daily\Day07_DCF指标采集\README.md"
git add ".\daily\Day08_DCF验证与调试\README.md"

git commit -m "docs: complete Day03-Day08 README files"
```
