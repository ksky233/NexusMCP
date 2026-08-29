import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";

test("browser drives publish, MCP call and audit through production-like Nginx", async ({
  page,
}) => {
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
  await operation.getByRole("button", { name: "审核 Operation" }).click();
  await operation.getByLabel("负责人").fill("people-platform");
  await operation.getByRole("button", { name: "接受并创建草稿" }).click();
  await operation.getByRole("button", { name: "提交审核" }).click();
  await operation.getByRole("button", { name: "发布版本" }).click();
  await page.getByRole("button", { name: "发布 Tool 版本" }).click();
  await expect(operation.getByText("已发布", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "工具目录" }).click();
  await expect(page.getByText("directory.get_employee", { exact: true })).toBeVisible();

  const repositoryRoot = path.resolve(process.cwd(), "..");
  execFileSync(
    "uv",
    [
      "run",
      "python",
      path.join(repositoryRoot, "tests", "e2e", "call_published_tool.py"),
      "http://127.0.0.1:8088/mcp",
    ],
    { cwd: repositoryRoot, stdio: "inherit" },
  );

  await page.getByRole("link", { name: "执行与审计" }).click();
  await expect(page.getByText("directory.get_employee", { exact: true })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByText("directory.get_employee", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Attempt 时间线" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "审计时间线" })).toBeVisible();
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
