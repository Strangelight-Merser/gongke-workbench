import {
  Tree,
  TreeItem,
  TreeItemLayout,
  Button,
} from "@fluentui/react-components";
import {
  DocumentRegular,
  FolderRegular,
  CubeRegular,
  CalculatorRegular,
  ClipboardTaskListLtrRegular,
  AddRegular,
} from "@fluentui/react-icons";
import {
  Project,
  ProjectFile,
  DocumentRef,
  fileGroup,
  cadDocument,
  revisionOf,
} from "./types";
const groups = ["图纸", "模型", "计算", "出图", "报告", "其他文件"];
export function ProjectTree({
  project,
  active,
  open,
  openFile,
  importFiles,
}: {
  project: Project | null;
  active: string;
  open(d: DocumentRef): void;
  openFile(f: ProjectFile): void;
  importFiles(): void;
}) {
  return (
    <aside className="project-pane" aria-label="工程树">
      <div className="panel-heading">
        <strong>工程</strong>
        <Button
          size="small"
          appearance="subtle"
          icon={<AddRegular />}
          aria-label="添加图纸"
          disabled={!project}
          onClick={importFiles}
        />
      </div>
      {project ? (
        <>
          <div className="project-name" title={project.path}>
            <FolderRegular />
            <strong>{project.name}</strong>
          </div>
          <Tree aria-label="工程对象" defaultOpenItems={groups} size="small">
            {groups.map((group) => {
              const files = project.files.filter((f) => fileGroup(f) === group);
              if (group === "其他文件" && !files.length) return null;
              const hasChildren =
                files.length > 0 || ["模型", "计算"].includes(group);
              return (
                <TreeItem
                  key={group}
                  value={group}
                  itemType={hasChildren ? "branch" : "leaf"}
                >
                  <TreeItemLayout
                    iconBefore={<FolderRegular />}
                    aside={
                      !["模型", "计算"].includes(group) ? (
                        <span className="muted">{files.length}</span>
                      ) : undefined
                    }
                  >
                    {group}
                  </TreeItemLayout>
                  {hasChildren && (
                    <Tree>
                      {group === "模型" && (
                        <TreeItem
                          itemType="leaf"
                          value="cad"
                          onClick={() => open(cadDocument)}
                        >
                          <TreeItemLayout
                            iconBefore={<CubeRegular />}
                            className={active === "cad" ? "tree-active" : ""}
                          >
                            原生 CAD
                          </TreeItemLayout>
                        </TreeItem>
                      )}
                      {group === "计算" && (
                        <TreeItem
                          itemType="leaf"
                          value="reducer"
                          onClick={() =>
                            open({
                              id: "reducer",
                              title: "减速器课程设计",
                              type: "reducer",
                            })
                          }
                        >
                          <TreeItemLayout
                            iconBefore={<CalculatorRegular />}
                            className={
                              active === "reducer" ? "tree-active" : ""
                            }
                          >
                            减速器课程设计
                          </TreeItemLayout>
                        </TreeItem>
                      )}
                      {files.map((file) => (
                        <TreeItem
                          key={file.path}
                          value={file.path}
                          itemType="leaf"
                          onClick={() => openFile(file)}
                        >
                          <TreeItemLayout
                            iconBefore={<DocumentRegular />}
                            className={
                              active === file.path ? "tree-active" : ""
                            }
                          >
                            <span title={file.path}>{file.name}</span>
                            {revisionOf(project, file)?.current === false && (
                              <span className="stale-mark">过期</span>
                            )}
                          </TreeItemLayout>
                        </TreeItem>
                      ))}
                    </Tree>
                  )}
                </TreeItem>
              );
            })}
            <TreeItem
              itemType="leaf"
              value="checks"
              onClick={() =>
                open({ id: "checks", title: "检查结果", type: "checks" })
              }
            >
              <TreeItemLayout iconBefore={<ClipboardTaskListLtrRegular />}>
                检查结果
              </TreeItemLayout>
            </TreeItem>
          </Tree>
        </>
      ) : (
        <p className="pane-empty">创建或打开工程后，图纸和模型会保存在这里。</p>
      )}
    </aside>
  );
}
