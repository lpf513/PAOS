import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  Bot,
  ChevronRight,
  FolderKanban,
  Loader2,
  Play,
  Plus,
  Terminal,
  X,
} from "lucide-react";

import AgentTerminal from "./components/AgentTerminal";
import DAGVisualizer from "./components/DAGVisualizer";
import "./App.css";
import {
  createProject,
  getProjectStatus,
  startProject,
} from "./services/api";
import type { DAGNode, ProjectStatusResponse } from "./types";

interface ProjectItem {
  id: number;
  name: string;
}

const POLLING_INTERVAL_MS = 2000;

function App() {
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<number | null>(null);
  const [projectStatus, setProjectStatus] = useState<ProjectStatusResponse | null>(null);
  const [dagNodes, setDagNodes] = useState<DAGNode[]>([]);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [rawContent, setRawContent] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const currentProject = useMemo(
    () => projects.find((project) => project.id === currentProjectId) ?? null,
    [currentProjectId, projects],
  );

  const syncProjectStatus = async (projectId: number) => {
    const status = await getProjectStatus(projectId);
    setProjectStatus(status);
    setDagNodes(status.nodes);
    return status;
  };

  useEffect(() => {
    if (!currentProjectId || !projectStatus?.is_running) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      syncProjectStatus(currentProjectId).catch((error: unknown) => {
        setErrorMessage(error instanceof Error ? error.message : "同步项目状态失败");
      });
    }, POLLING_INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, [currentProjectId, projectStatus?.is_running]);

  const handleCreateProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);
    setIsCreating(true);

    try {
      const createdProject = await createProject(projectName.trim(), rawContent.trim());
      const nextProject = {
        id: createdProject.project_id,
        name: projectName.trim(),
      };

      setProjects((currentProjects) => [nextProject, ...currentProjects]);
      setCurrentProjectId(createdProject.project_id);
      setProjectStatus(null);
      setDagNodes([]);
      setProjectName("");
      setRawContent("");
      setIsCreateModalOpen(false);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "创建项目失败");
    } finally {
      setIsCreating(false);
    }
  };

  const handleStartProject = async () => {
    if (!currentProjectId) {
      setErrorMessage("请先创建或选择一个项目。");
      return;
    }

    setErrorMessage(null);
    setIsStarting(true);

    try {
      await startProject(currentProjectId);
      await syncProjectStatus(currentProjectId);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "启动代理实例失败");
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <div className="min-h-screen overflow-hidden bg-[#0f172a] text-slate-100">
      <div className="flex h-screen flex-col lg:flex-row">
        <aside className="flex w-full shrink-0 flex-col border-b border-slate-800/80 bg-slate-950/70 backdrop-blur lg:w-[250px] lg:border-b-0 lg:border-r">
          <div className="flex h-20 items-center gap-3 border-b border-slate-800/80 px-5">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-300/30">
              <Bot size={24} />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-wide">PAOS</h1>
              <p className="text-xs uppercase tracking-[0.25em] text-slate-500">
                Agent OS
              </p>
            </div>
          </div>

          <div className="p-4">
            <button
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-950/40 transition hover:bg-cyan-300"
              onClick={() => setIsCreateModalOpen(true)}
              type="button"
            >
              <Plus size={18} />
              新建项目
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-3 pb-4">
            <div className="mb-3 flex items-center gap-2 px-2 text-xs font-medium uppercase tracking-[0.2em] text-slate-500">
              <FolderKanban size={14} />
              项目列表
            </div>
            <div className="space-y-2">
              {projects.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-800 px-3 py-6 text-center text-sm text-slate-500">
                  暂无项目，点击上方按钮创建。
                </div>
              ) : (
                projects.map((project) => {
                  const isSelected = project.id === currentProjectId;

                  return (
                    <button
                      className={`group w-full rounded-xl border px-3 py-3 text-left transition ${
                        isSelected
                          ? "border-cyan-400/40 bg-cyan-400/10"
                          : "border-slate-800 bg-slate-900/50 hover:border-slate-700 hover:bg-slate-900"
                      }`}
                      key={project.id}
                      onClick={() => {
                        setCurrentProjectId(project.id);
                        setProjectStatus(null);
                        setDagNodes([]);
                      }}
                      type="button"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="line-clamp-1 text-sm font-medium text-slate-100">
                          {project.name}
                        </span>
                        <ChevronRight
                          className="text-slate-600 transition group-hover:text-cyan-300"
                          size={16}
                        />
                      </div>
                      <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${
                            isSelected && projectStatus?.is_running
                              ? "bg-cyan-300"
                              : "bg-slate-600"
                          }`}
                        />
                        {isSelected && projectStatus?.is_running ? "运行中" : "待启动"}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col bg-slate-950/20">
          <header className="flex h-20 shrink-0 items-center justify-between border-b border-slate-800/80 px-6">
            <div>
              <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.2em] text-cyan-300">
                <Activity size={14} />
                当前项目
              </div>
              <h2 className="mt-1 text-xl font-semibold text-slate-50">
                {currentProject?.name ?? "尚未选择项目"}
              </h2>
            </div>
            <button
              className="flex items-center gap-2 rounded-xl bg-indigo-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-950/40 transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
              disabled={!currentProjectId || isStarting}
              onClick={handleStartProject}
              type="button"
            >
              {isStarting ? <Loader2 className="animate-spin" size={17} /> : <Play size={17} />}
              启动代理呼叫
            </button>
          </header>

          {errorMessage && (
            <div className="mx-6 mt-4 flex items-center gap-2 rounded-xl border border-rose-400/30 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
              <AlertCircle size={16} />
              {errorMessage}
            </div>
          )}

          <section className="flex min-h-0 flex-1 p-6">
            <div className="min-h-0 flex-1">
              <DAGVisualizer nodes={dagNodes} />
            </div>
          </section>
        </main>

        <aside className="flex w-full shrink-0 flex-col border-t border-slate-800/80 bg-slate-950/80 lg:w-[350px] lg:border-l lg:border-t-0">
          <div className="flex h-20 items-center gap-3 border-b border-slate-800/80 px-5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-400/10 text-emerald-300 ring-1 ring-emerald-300/30">
              <Terminal size={21} />
            </div>
            <div>
              <h2 className="font-semibold text-slate-100">终端与仲裁日志</h2>
              <p className="text-xs text-slate-500">Runtime Console</p>
            </div>
          </div>

          <div className="min-h-0 flex-1 p-4">
            <AgentTerminal />
          </div>
        </aside>
      </div>

      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur">
          <form
            className="w-full max-w-2xl rounded-3xl border border-slate-800 bg-slate-950 p-6 shadow-2xl shadow-black/40"
            onSubmit={handleCreateProject}
          >
            <div className="mb-6 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold text-slate-50">新建 PAOS 项目</h2>
                <p className="mt-1 text-sm text-slate-500">
                  输入项目名称和业务原始需求，系统会解析硬性约束并创建 IdentityGraph。
                </p>
              </div>
              <button
                className="rounded-xl p-2 text-slate-500 transition hover:bg-slate-900 hover:text-slate-200"
                onClick={() => setIsCreateModalOpen(false)}
                type="button"
              >
                <X size={20} />
              </button>
            </div>

            <label className="block text-sm font-medium text-slate-300" htmlFor="project-name">
              项目名称
            </label>
            <input
              className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-cyan-400"
              id="project-name"
              onChange={(event) => setProjectName(event.currentTarget.value)}
              placeholder="例如：智能客服体验优化"
              required
              value={projectName}
            />

            <label
              className="mt-5 block text-sm font-medium text-slate-300"
              htmlFor="raw-content"
            >
              业务原始需求
            </label>
            <textarea
              className="mt-2 min-h-[220px] w-full resize-none rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm leading-6 text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-cyan-400"
              id="raw-content"
              onChange={(event) => setRawContent(event.currentTarget.value)}
              placeholder="粘贴业务文档、约束、目标、合规要求等原始文本..."
              required
              value={rawContent}
            />

            <div className="mt-6 flex justify-end gap-3">
              <button
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-300 transition hover:bg-slate-900"
                onClick={() => setIsCreateModalOpen(false)}
                type="button"
              >
                取消
              </button>
              <button
                className="flex items-center gap-2 rounded-xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
                disabled={isCreating || !projectName.trim() || !rawContent.trim()}
                type="submit"
              >
                {isCreating && <Loader2 className="animate-spin" size={16} />}
                创建项目
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

export default App;
