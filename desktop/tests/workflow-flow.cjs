require("./helpers/generic-flow.cjs")
  .run("workflow")
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
