/** 仅转发到随包Core检查入口，不依赖当前工作目录或原仓库。 */
if (!process.argv[2]) {
  console.error('用法: node validate_core.mjs <建筑.wild>')
  process.exitCode = 2
} else {
  await import('../references/blueprint-kit/核心资料/wild-web/scripts/validate-generated.mjs')
}
