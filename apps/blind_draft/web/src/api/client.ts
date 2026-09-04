/**
 * 后端调用。**只有这一个文件知道 URL 长什么样。**
 *
 * dev 下 vite 把 /api 代理到 8621(见 vite.config.ts);打包成单文件之后
 * 页面由 bdserver 自己 serve,同源,相对路径照样能用。
 */
import type { DraftState, RunResult } from "./types";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // 后端把「越界动作」「预算不够」这类都算成 400 并带一句中文,直接透出来
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? `${path} 失败(HTTP ${res.status})`);
  }
  return res.json();
}

/** 放掉这个市场日。动作序列里用 -1 表示。 */
export const PASS = -1;

/**
 * 把一局盲选重放到给定动作之后的状态。
 *
 * 没有「下一步」这种接口——每次都提交完整的动作序列,后端从头重放。
 * 所以前端不持有任何局面状态,刷新页面也不会丢局。
 */
export const fetchDraft = (seed: number, actions: number[]) =>
  post<DraftState>("/api/draft", { seed, actions });

/** 把签满的五个 page 送进真实三段 Swiss,拿回玩家的一整届。 */
export const fetchRun = (pages: string[], seed: number) =>
  post<RunResult>("/api/run", { pages, seed });
