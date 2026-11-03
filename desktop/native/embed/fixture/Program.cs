internal static class Fixture
{
    [STAThread]
    static void Main()
    {
// 合成 Win32 窗口，仅验证窗口协议，不计为 CAD 验收。
Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
var form = new Form { Text = "Gongke synthetic fixture (not FreeCAD)", Width = 1000, Height = 700 };
var menu = new MenuStrip();
var file = new ToolStripMenuItem("文件(&F)");
var save = new ToolStripMenuItem("保存(&S)") { ShortcutKeys = Keys.Control | Keys.S };
var dialog = new ToolStripMenuItem("模态对话框(&O)") { ShortcutKeys = Keys.Control | Keys.O };
var floating = new ToolStripMenuItem("浮动面板");
var dirty = false;
var text = new TextBox { Multiline = true, Dock = DockStyle.Fill, AccessibleName = "fixture-editor" };
text.TextChanged += (_, _) => dirty = true;
save.Click += (_, _) => { dirty = false; form.Text = "Gongke synthetic fixture saved"; };
dialog.Click += (_, _) => MessageBox.Show(form, "测试保存、取消、焦点和跨屏布局", "原生模态对话框", MessageBoxButtons.OKCancel);
floating.Click += (_, _) => new Form { Text = "原生浮动面板", Width = 300, Height = 200, ShowInTaskbar = false }.Show(form);
file.DropDownItems.AddRange([save, dialog, floating]); menu.Items.Add(file); form.MainMenuStrip = menu;
form.Controls.Add(text); form.Controls.Add(menu);
form.FormClosing += (_, e) => { if (dirty && MessageBox.Show(form, "放弃替身窗口的未保存文字？", "未保存", MessageBoxButtons.OKCancel) == DialogResult.Cancel) e.Cancel = true; };
Application.Run(form);

    }
}
