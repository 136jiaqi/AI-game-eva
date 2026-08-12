import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "XMODhub AI 免费评估",
  description: "提交单机游戏修改器需求，获取 AI 免费评估结果。",
};

export default function Home() {
  return (
    <main className="portal-shell" aria-label="AI 免费评估页">
      <iframe
        src="/h5/index.html"
        title="XMODhub AI 免费评估页"
        className="portal-iframe"
      />
    </main>
  );
}
