const {defineConfig,devices}=require('@playwright/test');
module.exports=defineConfig({testDir:'./tests/ui',workers:1,retries:0,timeout:60000,use:{baseURL:process.env.BASE_URL||'http://localhost:8080',...devices['iPhone 13'],browserName:'chromium',trace:'retain-on-failure',screenshot:'only-on-failure'},reporter:[['list'],['html',{open:'never'}]],outputDir:'test-results'});
