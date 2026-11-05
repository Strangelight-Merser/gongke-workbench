// 独立原生 PDF 阅读器窗口；不加载工作台、不修改 PDF。
const {app,BrowserWindow}=require('electron');
app.whenReady().then(async()=>{
 const win=new BrowserWindow({width:1920,height:1080,webPreferences:{plugins:true}});
 await win.loadFile(process.env.GONGKE_DEMO_PDF);
});
app.on('window-all-closed',()=>app.quit());
