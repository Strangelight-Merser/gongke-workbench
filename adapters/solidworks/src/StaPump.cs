using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Gongke.SolidWorks
{
    // 在 ConnectToSW 所在的宿主 STA 线程创建仅消息窗口；管道线程投递消息，命令回到宿主线程执行。
    internal sealed class StaPump : NativeWindow
    {
        private const int WmRun = 0x8000 + 0x21;
        private readonly Action run;
        public StaPump(Action run)
        {
            this.run = run;
            CreateHandle(new CreateParams { Caption = "GongkeStaPump", Parent = new IntPtr(-3) });
        }
        public void Post() => PostMessage(Handle, WmRun, IntPtr.Zero, IntPtr.Zero);
        protected override void WndProc(ref Message m)
        {
            if (m.Msg == WmRun) run();
            else base.WndProc(ref m);
        }
        [DllImport("user32.dll")] private static extern bool PostMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);
    }
}
