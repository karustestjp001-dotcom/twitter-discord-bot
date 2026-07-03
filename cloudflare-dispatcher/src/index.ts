interface Env {
  GITHUB_TOKEN: string;
  GITHUB_OWNER: string;
  GITHUB_REPO: string;
  GITHUB_WORKFLOW_ID: string;
  GITHUB_REF: string;
  TRIGGER_SECRET?: string;
  DISCORD_HEALTH_WEBHOOK?: string;
}

type DispatchResult = {
  ok: boolean;
  status: number;
  message: string;
};

const githubApiVersion = "2022-11-28";

export default {
  async scheduled(controller: ScheduledController, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(runDispatch(env, `cron:${controller.cron}`));
  },

  async fetch(request: Request, env: Env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return json({ ok: true, service: "twitter-discord-bot-dispatcher" });
    }

    if (url.pathname !== "/dispatch") {
      return json({ ok: false, error: "not found" }, 404);
    }

    if (request.method !== "POST") {
      return json({ ok: false, error: "method not allowed" }, 405);
    }

    if (!isAuthorized(request, env, url)) {
      return json({ ok: false, error: "unauthorized" }, 401);
    }

    const result = await runDispatch(env, "manual-http");
    return json(result, result.ok ? 200 : 502);
  },
};

async function runDispatch(env: Env, source: string): Promise<DispatchResult> {
  try {
    const result = await dispatchGithubWorkflow(env, source);
    if (!result.ok) {
      await notifyDiscord(env, `GitHub workflow_dispatch failed (${result.status}): ${result.message}`);
    }
    return result;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await notifyDiscord(env, `Cloudflare dispatcher error: ${message}`);
    return { ok: false, status: 500, message };
  }
}

async function dispatchGithubWorkflow(env: Env, source: string): Promise<DispatchResult> {
  const owner = env.GITHUB_OWNER;
  const repo = env.GITHUB_REPO;
  const workflowId = encodeURIComponent(env.GITHUB_WORKFLOW_ID);
  const ref = env.GITHUB_REF || "main";
  const endpoint = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflowId}/dispatches`;

  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Content-Type": "application/json",
      "User-Agent": "twitter-discord-bot-dispatcher",
      "X-GitHub-Api-Version": githubApiVersion,
    },
    body: JSON.stringify({
      ref,
      inputs: {
        source,
      },
    }),
  });

  if (response.status === 204) {
    return { ok: true, status: response.status, message: "workflow dispatched" };
  }

  const body = await response.text();
  return {
    ok: false,
    status: response.status,
    message: body || response.statusText,
  };
}

function isAuthorized(request: Request, env: Env, url: URL): boolean {
  if (!env.TRIGGER_SECRET) {
    return false;
  }

  const auth = request.headers.get("Authorization");
  const token = url.searchParams.get("token");
  return auth === `Bearer ${env.TRIGGER_SECRET}` || token === env.TRIGGER_SECRET;
}

async function notifyDiscord(env: Env, content: string): Promise<void> {
  if (!env.DISCORD_HEALTH_WEBHOOK) {
    return;
  }

  await fetch(env.DISCORD_HEALTH_WEBHOOK, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}
