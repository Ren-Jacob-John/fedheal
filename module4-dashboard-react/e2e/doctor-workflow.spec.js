import { expect, test } from "@playwright/test";

const authApi = process.env.FEDHEAL_E2E_AUTH_API_URL || "http://localhost:8001";
const superAdminEmail = process.env.FEDHEAL_E2E_SUPER_ADMIN_EMAIL;
const superAdminPassword = process.env.FEDHEAL_E2E_SUPER_ADMIN_PASSWORD;

async function signIn(page, email, password) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Enter the federation" }).click();
}

test("super admin provisions a hospital; doctor completes case, analysis and review", async ({ page, request }) => {
  test.setTimeout(90_000);
  test.skip(!superAdminEmail || !superAdminPassword, "Set the E2E super-admin email and password.");

  const adminLogin = await request.post(`${authApi}/token`, {
    form: { username: superAdminEmail, password: superAdminPassword },
  });
  expect(adminLogin.ok(), "super-admin credentials must be provisioned on the target stack").toBeTruthy();
  const { access_token: adminToken } = await adminLogin.json();

  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  const hospitalResponse = await request.post(`${authApi}/hospitals`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: { name: `PW synthetic hospital ${suffix}` },
  });
  expect(hospitalResponse.status()).toBe(200);
  const hospital = await hospitalResponse.json();

  const hospitalAdminEmail = `pw-admin-${suffix}@example.test`;
  const hospitalAdminPassword = `pw-admin-${suffix}-Pass1!`;
  const hospitalAdminResponse = await request.post(`${authApi}/admin/users`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: {
      email: hospitalAdminEmail,
      password: hospitalAdminPassword,
      role: "hospital_admin",
      hospital_id: hospital.id,
    },
  });
  expect(hospitalAdminResponse.status()).toBe(200);

  await signIn(page, hospitalAdminEmail, hospitalAdminPassword);
  await expect(page.getByRole("button", { name: "Doctors", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Doctors", exact: true }).click();
  await page.getByLabel("Full name").fill("Synthetic E2E Doctor");
  const doctorEmail = `pw-doctor-${suffix}@example.test`;
  const doctorPassword = `pw-doctor-${suffix}-Pass1!`;
  await page.getByLabel("Email").fill(doctorEmail);
  await page.getByLabel("Initial password (min 10)").fill(doctorPassword);
  await page.getByRole("button", { name: "Create doctor" }).click();
  await expect(page.getByRole("status")).toContainText("Doctor created.");

  const logoutResponse = page.waitForResponse(
    (response) => response.url() === `${authApi}/logout` && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Log out" }).click();
  await logoutResponse;
  await signIn(page, doctorEmail, doctorPassword);
  await expect(page.getByRole("button", { name: "Cases", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cases", exact: true }).click();

  const caseForm = page.getByRole("form", { name: "Create case" });
  await caseForm.getByLabel("Patient reference (synthetic id)").fill(`PW-DEMO-${suffix}`);
  await caseForm.getByLabel("Admission reason").fill("Synthetic end-to-end workflow test");
  await caseForm.getByLabel("Presenting symptoms (one per line)").fill("synthetic-only test entry");
  await caseForm.getByRole("button", { name: "Create case" }).click();

  const vitalsForm = page.getByRole("form", { name: "Vitals" });
  for (const [label, value] of [
    ["Age (years)", "58"],
    ["Height (cm)", "172"],
    ["Weight (kg)", "80"],
    ["Systolic BP", "150"],
    ["Diastolic BP", "90"],
    ["Heart rate (bpm)", "100"],
    ["Medication count", "0"],
    ["Medication total (mg)", "0"],
  ]) {
    await vitalsForm.getByLabel(label).fill(value);
  }
  await vitalsForm.getByRole("button", { name: "Validate & save vitals" }).click();
  await expect(vitalsForm.getByRole("status")).toContainText("Vitals validated and saved.");

  const historyForm = page.getByRole("form", { name: "Medical history" });
  await historyForm.getByLabel("Previous diagnoses").fill("synthetic-only test entry");
  await historyForm.getByRole("button", { name: "Save medical history" }).click();
  await expect(historyForm.getByRole("status")).toContainText("Medical history saved.");

  await page.getByRole("button", { name: "Run AI analysis" }).click();
  const report = page.locator('[aria-label="AI report"]');
  await expect(report).toBeVisible();
  await expect(report.getByText("FALLBACK", { exact: true })).toBeVisible();
  await expect(report.getByText(/fallback\/demo model: not a validated clinical result\./)).toBeVisible();
  await expect(report).toContainText("Final clinical decisions must be made by a qualified healthcare professional.");
  await expect(page.getByRole("region", { name: "Analysis history" })).toContainText("current report");

  const reviewForm = page.getByRole("form", { name: "Clinician review" });
  await expect(reviewForm).toContainText("This review will be linked to analysis");
  await reviewForm.getByLabel("Decision").selectOption("ACCEPTED");
  await reviewForm.getByLabel("Note").fill("Synthetic E2E review; not a training label.");
  await reviewForm.getByRole("button", { name: "Submit review" }).click();
  await expect(reviewForm.getByRole("status")).toContainText("Review recorded.");
});
