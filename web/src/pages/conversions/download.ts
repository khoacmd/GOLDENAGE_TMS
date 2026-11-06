/** Tải file Excel trả về dạng base64 từ API chuyển đổi. */
export function download(result: { filename: string; content_base64: string }) {
  const bytes = Uint8Array.from(atob(result.content_base64), (c) => c.charCodeAt(0))
  const url = URL.createObjectURL(
    new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
  )
  const a = document.createElement('a')
  a.href = url
  a.download = result.filename
  a.click()
  URL.revokeObjectURL(url)
}
