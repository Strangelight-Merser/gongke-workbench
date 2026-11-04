import {
  Button,
  Tab,
  TabList,
  Menu,
  MenuTrigger,
  MenuPopover,
  MenuList,
  MenuItem,
} from "@fluentui/react-components";
import {
  DismissRegular,
  DocumentRegular,
  CubeRegular,
} from "@fluentui/react-icons";
import { DocumentRef } from "../project/types";
export function DocumentTabs({
  documents,
  active,
  select,
  close,
  pin,
}: {
  documents: DocumentRef[];
  active: string;
  select(id: string): void;
  close(id: string): void;
  pin(id: string): void;
}) {
  return (
    <div className="document-tabs">
      <TabList
        size="small"
        selectedValue={active}
        onTabSelect={(_, d) => select(String(d.value))}
        aria-label="文档标签"
      >
        {documents.map((doc) => (
          <Menu openOnContext key={doc.id}>
            <MenuTrigger disableButtonEnhancement>
              <div
                className={
                  "document-tab " +
                  (active === doc.id ? "active " : "") +
                  (doc.preview ? "preview" : "")
                }
                onDoubleClick={() => pin(doc.id)}
                title={doc.file?.path || doc.title}
                key={doc.id}
              >
                <Tab
                  value={doc.id}
                  icon={
                    doc.type === "cad" ? <CubeRegular /> : <DocumentRegular />
                  }
                >
                  {doc.title}
                </Tab>
                <Button
                  size="small"
                  appearance="subtle"
                  icon={<DismissRegular />}
                  aria-label={"关闭 " + doc.title}
                  onClick={() => close(doc.id)}
                />
              </div>
            </MenuTrigger>
            <MenuPopover>
              <MenuList>
                <MenuItem disabled={!doc.preview} onClick={() => pin(doc.id)}>
                  保留标签
                </MenuItem>
                <MenuItem onClick={() => close(doc.id)}>关闭标签</MenuItem>
              </MenuList>
            </MenuPopover>
          </Menu>
        ))}
      </TabList>
    </div>
  );
}
