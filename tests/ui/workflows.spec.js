const {test,expect}=require('@playwright/test');
const fs=require('node:fs/promises');
async function capture(page,name){await fs.mkdir('docs/runtime-screenshots',{recursive:true});await page.screenshot({path:`docs/runtime-screenshots/${name}.png`});}
async function register(page){
 await page.goto('/register');
 await page.getByLabel('Full name',{exact:true}).fill('UI Test Owner');
 await page.getByLabel('Phone number',{exact:true}).fill('+614'+String(Date.now()).slice(-8));
 await page.getByLabel('Email address',{exact:true}).fill('ui'+Date.now()+'@example.com');
 await page.getByLabel('Password (at least 6 characters)',{exact:true}).fill('test-only-secure-password');
 await page.getByRole('button',{name:'Create account',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Your money, clear.'})).toBeVisible();
}
async function contact(page,name){
 await page.goto('/people#new');await page.getByLabel('Full name',{exact:true}).fill(name);
 await page.getByRole('button',{name:'Save person',exact:true}).click();await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
}

test('mobile personal ledger, partial repayment, themes, and search',async({page})=>{
 await register(page);await capture(page,'home-light');
 await page.getByRole('button',{name:'Toggle dark mode'}).click();await expect(page.locator('#device')).toHaveClass(/dark/);
 await page.reload();await expect(page.locator('#device')).toHaveClass(/dark/);await capture(page,'home-dark');
 await contact(page,'Test Sahil');const personUrl=page.url();
 await page.getByRole('link',{name:'＋ Entry / repayment',exact:true}).click();
 await page.getByLabel('Amount (AUD)',{exact:true}).fill('100');await page.getByLabel('Description',{exact:true}).fill('UI dinner');
 await page.getByRole('button',{name:'Save transaction',exact:true}).click();await expect(page.getByText('$100.00',{exact:true}).first()).toBeVisible();
 await page.getByRole('link',{name:'＋ Entry / repayment',exact:true}).click();await page.locator('select[name="kind"]').selectOption('repayment_received');
 await page.getByLabel('Amount (AUD)',{exact:true}).fill('30');await page.getByRole('button',{name:'Save transaction',exact:true}).click();
 await expect(page.getByText('$70.00',{exact:true})).toBeVisible();await capture(page,'person-dark');
 await page.goto('/search');await page.getByLabel('People, transactions, groups and bills',{exact:true}).fill('UI dinner');await page.getByRole('button',{name:'Search',exact:true}).click();await expect(page.getByRole('link',{name:'UI dinner →'})).toBeVisible();
 await page.goto(personUrl);expect(await page.locator('.screen').evaluate(e=>e.scrollWidth<=e.clientWidth)).toBeTruthy();
});

test('split, isolated group expense, review, and finalization',async({page})=>{
 await register(page);await contact(page,'Test Priya');await contact(page,'Test Alex');
 await page.goto('/split');await page.getByLabel('Description',{exact:true}).fill('Equal split');await page.getByLabel('Total (AUD)',{exact:true}).fill('100');
 await page.getByRole('button',{name:'Post split',exact:true}).click();await expect(page.getByRole('heading',{name:'Equal split'})).toBeVisible();await expect(page.getByText('$33.34',{exact:true})).toBeVisible();
 await page.goto('/');const before=await page.locator('.hero .total').innerText();
 await page.goto('/groups#new');await page.getByLabel('Group name',{exact:true}).fill('UI Trip');for(const checkbox of await page.locator('input[name="participants"]').all())await checkbox.check();
 await page.getByRole('button',{name:'Create group',exact:true}).click();const groupUrl=page.url();
 await page.getByRole('link',{name:'＋ Expense',exact:true}).click();await page.getByLabel('Description',{exact:true}).fill('Hotel');await page.getByLabel('Total (AUD)',{exact:true}).fill('90');await page.getByRole('button',{name:'Save expense',exact:true}).click();
 await page.goto('/');await expect(page.locator('.hero .total')).toHaveText(before);
 await page.goto(groupUrl);await page.getByRole('button',{name:'Request review',exact:true}).click();await capture(page,'group-review');await page.locator('input[name="confirm"]').check();await page.getByRole('button',{name:'Finalize group',exact:true}).click();await expect(page.getByText('Finalized',{exact:true})).toBeVisible();
 await page.goto('/');await expect(page.locator('.hero .total')).not.toHaveText(before);
 for(const path of ['/people','/add','/groups','/activity','/profile']){await page.goto(path);await expect(page.locator('h2')).toBeVisible();expect(await page.locator('.screen').evaluate(e=>e.scrollWidth<=e.clientWidth)).toBeTruthy();}
});

test('PWA manifest, browser validation, and safe offline fallback',async({page,context})=>{
 await page.goto('/register');await page.getByRole('button',{name:'Create account',exact:true}).click();await expect(page).toHaveURL(/register/);
 const manifest=await (await page.request.get('/static/manifest.webmanifest')).json();expect(manifest.display).toBe('standalone');expect(manifest.icons).toHaveLength(2);
 await page.evaluate(()=>navigator.serviceWorker.ready);await page.reload();await context.setOffline(true);await page.reload();await expect(page.getByRole('heading',{name:"You're offline."})).toBeVisible();await capture(page,'offline');await context.setOffline(false);
});
