import { expect, test, type Page } from "@playwright/test";

test.describe.serial("role registration and access", () => {
  const stamp = Date.now();
  const studentEmail = `student.${stamp}@gmail.com`;
  const teacherEmail = `teacher.${stamp}@mail.ru`;
  const parentEmail = `parent.${stamp}@yandex.ru`;
  const password = "StrongPass123!";

  async function registerRole(
    page: Page,
    role: "student" | "teacher" | "parent",
    fullName: string,
    email: string,
  ) {
    await page.goto("/auth?mode=register", { waitUntil: "domcontentloaded" });
    await page.locator("select").selectOption(role);
    await page.getByLabel("Имя и фамилия").fill(fullName);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Пароль").fill(password);
    await page.getByRole("button", { name: "Создать аккаунт" }).click();
    await expect(page).toHaveURL(new RegExp(`/dashboard/${role}`));
  }

  test("student can register and see guidance", async ({ page }) => {
    await registerRole(page, "student", "Тестовый Ученик", studentEmail);
    await expect(page.getByText("Как пользоваться: быстрый маршрут")).toBeVisible();
    await page.getByRole("button", { name: "Выйти" }).click();
    await expect(page).toHaveURL(/\/auth\?mode=login$/);
  });

  test("teacher can register and link student by email", async ({ page }) => {
    await registerRole(page, "teacher", "Тестовый Учитель", teacherEmail);
    await page.getByPlaceholder("student@example.com").fill(studentEmail);
    await page.getByRole("button", { name: "Подключить ученика" }).click();
    await expect(page.getByText("Маршрут учителя")).toBeVisible();
  });

  test("parent can register and open feed", async ({ page }) => {
    await registerRole(page, "parent", "Тестовый Родитель", parentEmail);
    await page.getByPlaceholder("student@example.com").fill(studentEmail);
    await page.getByRole("button", { name: "Подключить" }).click();
    await expect(page.getByText("Сигналы и уведомления")).toBeVisible();
  });
});
