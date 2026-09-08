import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";

test("browser drives publish, MCP call and audit through production-like Nginx", async ({
  page,
}) => {
  const repositoryRoot = path.resolve(process.cwd(), "..");
  execFileSync(
    "uv",
    ["run", "python", path.join(repositoryRoot, "tests", "e2e", "seed_web_control_plane.py")],
    { cwd: repositoryRoot, stdio: "inherit" },
  );

  await page.goto("/");
  await expect(page.getByText("本地开发管理员 · 非生产级身份认证")).toBeVisible();

  await page.getByRole("link", { name: "上游服务" }).click();
  await page.getByRole("button", { name: "注册上游服务" }).click();
  const registrationForm = page.locator("form");
  await registrationForm.getByLabel("Namespace").fill("directory");
  await registrationForm.getByLabel("名称", { exact: true }).fill("employee-directory-e2e");
  await registrationForm.getByLabel("负责人").fill("people-platform");
  await registrationForm.getByLabel("Endpoint").fill("http://127.0.0.1:9001");
  await registrationForm.getByRole("button", { name: "注册上游服务" }).click();
  await expect(
    page.getByRole("heading", { name: "directory.employee-directory-e2e" }),
  ).toBeVisible();

  await page.getByRole("link", { name: "导入与审核" }).click();
  await page.getByRole("button", { name: "新建导入" }).click();
  await page
    .getByLabel("已启用上游服务")
    .selectOption({ label: "directory.employee-directory-e2e" });
  await page.getByRole("button", { name: "提交导入" }).click();
  await expect(page.getByText("getEmployee", { exact: true })).toBeVisible();

  const operation = page.locator("article").filter({ hasText: "getEmployee" });
  await operation.getByRole("button", { name: "直接发布" }).click();
  await operation.getByLabel("负责人").fill("people-platform");
  await operation.getByRole("button", { name: "确认并直接发布" }).click();
  await expect(operation.getByText("已发布", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "工具目录" }).click();
  await expect(page.getByText("directory.get_employee", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "工具集" }).click();
  await page.getByRole("button", { name: "创建工具集" }).click();
  const toolsetForm = page.locator("form");
  await toolsetForm.getByLabel("Slug").fill("people-directory-e2e");
  await toolsetForm.getByLabel("名称", { exact: true }).fill("People Directory E2E");
  await toolsetForm.getByRole("button", { name: "创建草稿" }).click();
  await expect(page.getByRole("heading", { name: "People Directory E2E" })).toBeVisible();

  const member = page.getByRole("checkbox", { name: /directory\.get_employee/ });
  await member.check();
  await page.getByRole("button", { name: "保存成员" }).click();
  await expect(page.getByText("健康", { exact: true })).toBeVisible();

  await page.getByLabel("Principal IDs").fill("local-agent-service");
  await page.getByRole("button", { name: "保存 Grant" }).click();
  await expect(page.getByText(/Revision 3/)).toBeVisible();
  await page.getByRole("button", { name: "启用" }).click();
  await expect(page.getByText("已启用", { exact: true }).first()).toBeVisible();

  execFileSync(
    "uv",
    [
      "run",
      "python",
      path.join(repositoryRoot, "tests", "e2e", "call_published_tool.py"),
      "http://127.0.0.1:8088/mcp/toolsets/people-directory-e2e",
    ],
    { cwd: repositoryRoot, stdio: "inherit" },
  );

  await page.getByRole("link", { name: "执行与审计" }).click();
  const executionLink = page.getByRole("link", {
    name: "directory.get_employee",
    exact: true,
  });
  await expect(executionLink).toBeVisible({
    timeout: 30_000,
  });
  await executionLink.click();
  await expect(page.getByRole("heading", { name: "Attempt 时间线" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "审计时间线" })).toBeVisible();
  await expect(page.getByText("Toolset · revision 4", { exact: true })).toBeVisible();
  await expect(page.getByText(/Scope：toolset · active_toolset_grant/).first()).toBeVisible();
  await expect(page.getByText("成功", { exact: true }).first()).toBeVisible();
});

test("Nginx preserves SPA fallback, security headers and mobile navigation", async ({
  page,
  request,
}) => {
  const response = await request.get("/catalog/nonexistent");
  expect(response.status()).toBe(200);
  expect(response.headers()["content-security-policy"]).toContain("default-src 'self'");
  expect(response.headers()["x-frame-options"]).toBe("DENY");
  expect(response.headers()["x-content-type-options"]).toBe("nosniff");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("dialog", { name: "控制台导航" })).toBeVisible();
  await expect(page.getByRole("link", { name: "工程证据" }).last()).toBeVisible();
  await page.getByRole("button", { name: "关闭导航" }).click();
  await expect(page.getByRole("dialog", { name: "控制台导航" })).not.toBeVisible();
});
