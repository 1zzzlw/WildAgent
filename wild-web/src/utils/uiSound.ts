/** 按用户选择启用短提示音；不下载音频、不在后台播放。 */
let context: AudioContext | undefined
export function playUISound(kind: 'tap' | 'save' | 'error' = 'tap') {
  try {
    if (localStorage.getItem('wild_editor_sound') !== 'true') return
    context ??= new AudioContext()
    void context.resume()
    const oscillator = context.createOscillator()
    const gain = context.createGain()
    const now = context.currentTime
    oscillator.type = 'sine'
    oscillator.frequency.setValueAtTime(kind === 'save' ? 660 : kind === 'error' ? 220 : 440, now)
    oscillator.frequency.exponentialRampToValueAtTime(kind === 'save' ? 990 : 330, now + .07)
    gain.gain.setValueAtTime(.025, now)
    gain.gain.exponentialRampToValueAtTime(.0001, now + .10)
    oscillator.connect(gain).connect(context.destination)
    oscillator.start(now)
    oscillator.stop(now + .11)
  } catch { /* 浏览器不支持音频时，编辑操作仍正常完成。 */ }
}
