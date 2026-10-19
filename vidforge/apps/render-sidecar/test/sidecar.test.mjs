import test from "node:test";
import assert from "node:assert/strict";
import { hiddenSpawn } from "../src/sidecar.mjs";

test("hiddenSpawn spawns child process with windowsHide enabled", async () => {
  const proc = hiddenSpawn(process.execPath, ["-e", "process.stdout.write('ok')"]);
  let out = "";
  proc.stdout.on("data", (d) => {
    out += d.toString();
  });
  const code = await new Promise((res) => proc.on("close", res));
  assert.equal(code, 0);
  assert.equal(out, "ok");
});
