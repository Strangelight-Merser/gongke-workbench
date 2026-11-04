require("./helpers/generic-flow.cjs")
  .run("desktop")
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
