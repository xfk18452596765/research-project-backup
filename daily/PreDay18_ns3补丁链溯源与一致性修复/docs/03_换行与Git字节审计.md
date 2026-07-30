# 换行与 Git 字节审计

`.gitattributes` 不存在；配置来源记录在 `results/audit/line_ending_audit.json`。`git ls-files --eol` 对三份补丁均报告 index 为 LF、工作区为 CRLF。三份文件均无 UTF-8 BOM 且均有尾部换行。完整原始与归一化 SHA 位于 `patch_history.json`。
