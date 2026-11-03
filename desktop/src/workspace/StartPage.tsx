import { Button } from "@fluentui/react-components";
import {
  CubeRegular,
  DocumentAddRegular,
  FolderOpenRegular,
  AddRegular,
} from "@fluentui/react-icons";
import { Project } from "../project/types";
export function StartPage({
  project,
  choose,
  importFiles,
  model,
}: {
  project: Project | null;
  choose(create: boolean): void;
  importFiles(): void;
  model(): void;
}) {
  return (
    <div className="start-page">
      <div className="start-content">
        <h1>{project ? project.name : "构想引擎"}</h1>
        <p className="start-intro">
          {project
            ? "从图纸开始，或直接进入建模。"
            : "打开工程，继续你的设计。"}
        </p>
        <div className="start-actions">
          {project ? (
            <>
              <Button
                appearance="primary"
                icon={<DocumentAddRegular />}
                onClick={importFiles}
              >
                打开图纸
              </Button>
              <Button icon={<CubeRegular />} onClick={model}>
                新建模型
              </Button>
            </>
          ) : (
            <>
              <Button
                appearance="primary"
                icon={<AddRegular />}
                onClick={() => choose(true)}
              >
                新建工程
              </Button>
              <Button
                icon={<FolderOpenRegular />}
                onClick={() => choose(false)}
              >
                打开工程
              </Button>
            </>
          )}
        </div>
        {project && (
          <div className="start-guide">
            <h2>照图建模</h2>
            <ol>
              <li>打开 PDF、图片或 DXF 图纸</li>
              <li>在右侧告诉 Agent 要建立的模型</li>
              <li>在 CAD 中查看特征，检查后继续编辑</li>
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}
