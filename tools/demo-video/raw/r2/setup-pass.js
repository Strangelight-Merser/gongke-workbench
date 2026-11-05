await page.evaluate(p=>window.gongke.request('project.open',{path:p}),path.join(out,'project'));

await page.reload();await page.getByText('就绪',{exact:true}).waitFor();
if(await page.getByRole('button',{name:'展开工程树',exact:true}).count())await click(page,page.getByRole('button',{name:'展开工程树',exact:true}));
await click(page,page.getByText('原生 CAD',{exact:true}));await click(page,page.getByRole('button',{name:'连接 FreeCAD',exact:true}));
await click(page,page.getByRole('button',{name:'Agent 连接设置',exact:true}));await click(page,page.getByRole('menuitem',{name:'使用已配置的 Agent',exact:true}));
await click(page,page.getByRole('button',{name:'收起工程树',exact:true}));
await click(page,page.getByRole('button',{name:'读取 FreeCAD 工程',exact:true}));
const canvas=page.locator('.model-view canvas'),b=await canvas.boundingBox();
await page.mouse.move(b.x+b.width*.4,b.y+b.height*.4,{steps:24});await page.mouse.down();
await page.mouse.move(b.x+b.width*.4+b.height/8,b.y+b.height*.7,{steps:60});await page.mouse.up();await pause(1200);
