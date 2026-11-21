export type ApiResult = { status: number; body: Record<string, unknown> }

export function mailHelp(mode: unknown) {
  if (mode === 'smtp') return {
    title: '학교 메일에서 인증번호 확인',
    description: '입력한 @syuin.ac.kr 메일의 수신함을 확인하세요. 보이지 않으면 스팸함도 확인해 주세요.',
    sent: '인증메일 발송 요청을 접수했습니다. 잠시 후 학교 메일 수신함과 스팸함을 확인해 주세요.',
  }
  if (mode === 'file') return {
    title: '개발용 메일 파일 확인',
    description: '파일 메일 모드입니다. VS Code에서 .local/mail/ 폴더의 최신 파일을 열고 해당 수신 주소의 인증번호를 입력하세요.',
    sent: '인증메일 발송을 접수했습니다. 개발용 메일 파일에서 번호를 확인해 주세요.',
  }
  return {
    title: '인증메일 확인',
    description: '메일 확인 방식을 확인하고 있습니다. 안내가 갱신되지 않으면 CSRF 연결 갱신을 눌러 주세요.',
    sent: '인증메일 발송 요청을 접수했습니다. 메일 확인 방식을 확인해 주세요.',
  }
}

export async function apiRequest(path: string, payload?: Record<string, unknown>, csrf?: string): Promise<ApiResult> {
  const headers: Record<string, string> = {}
  if (payload !== undefined) headers['Content-Type'] = 'application/json'
  if (csrf) headers['X-CSRFToken'] = csrf
  const response = await fetch(`/api/v1/auth/${path}`, {
    method: payload === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers,
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new Error('API의 JSON 응답을 받지 못했습니다. Django(8000) 실행과 Vite 프록시를 확인해 주세요.')
  }
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw new Error('API 응답 형식을 확인해 주세요.')
  }
  return { status: response.status, body: body as Record<string, unknown> }
}
