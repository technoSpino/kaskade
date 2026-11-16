# Deployment Guide

This guide covers deploying your German Declension Learning App to either GitHub Pages or Netlify.

---

## Prerequisites

- Completed app in `app/` directory
- All files tested locally
- Git installed
- GitHub account (for both options)

---

## Option 1: Netlify (Recommended)

### Why Netlify?
- ✅ Easiest deployment process
- ✅ Instant preview URLs
- ✅ Automatic deployments on git push
- ✅ Free SSL certificate
- ✅ Custom domain support (free)
- ✅ Form handling (if needed later)
- ✅ No branch management needed

### Method A: Drag & Drop (Fastest)

1. **Go to Netlify**
   - Visit https://app.netlify.com/
   - Sign up or log in (can use GitHub account)

2. **Deploy**
   - Click "Add new site" → "Deploy manually"
   - Drag the `app/` folder into the upload area
   - Wait ~30 seconds
   - Done! You'll get a URL like: https://random-name-12345.netlify.app

3. **Custom Domain** (Optional)
   - Click "Domain settings"
   - Click "Add custom domain"
   - Follow instructions (free with Netlify)

### Method B: Git-Connected (Best for ongoing development)

1. **Push to GitHub**
   ```bash
   # In project root
   git init
   git add .
   git commit -m "Initial commit"
   
   # Create repo on GitHub, then:
   git remote add origin https://github.com/YOUR_USERNAME/kaskade.git
   git push -u origin main
   ```

2. **Connect to Netlify**
   - Go to https://app.netlify.com/
   - Click "Add new site" → "Import an existing project"
   - Choose "GitHub"
   - Select your repository
   - Configure:
     - **Base directory:** Leave empty
     - **Build command:** Leave empty (static site)
     - **Publish directory:** `app`
   - Click "Deploy"

3. **Automatic Updates**
   - Every git push triggers automatic redeployment
   - Netlify builds and deploys in ~1 minute

### Method C: Netlify CLI

1. **Install CLI**
   ```bash
   npm install -g netlify-cli
   # or
   brew install netlify-cli
   ```

2. **Login**
   ```bash
   netlify login
   # Opens browser for authentication
   ```

3. **Deploy**
   ```bash
   cd app/
   netlify deploy
   # Follow prompts
   # For production:
   netlify deploy --prod
   ```

### Netlify Configuration File (Optional)

Create `netlify.toml` in project root:

```toml
[build]
  publish = "app"
  
[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200

[build.environment]
  NODE_VERSION = "18"

[[headers]]
  for = "/*"
  [headers.values]
    X-Frame-Options = "DENY"
    X-XSS-Protection = "1; mode=block"
    X-Content-Type-Options = "nosniff"
```

---

## Option 2: GitHub Pages

### Why GitHub Pages?
- ✅ Free hosting
- ✅ Integrates with GitHub repos
- ✅ Good for open source projects
- ⚠️ Slightly more complex setup
- ⚠️ Requires branch management

### Method A: Using gh-pages Branch

1. **Prepare Repository**
   ```bash
   # In project root
   git init
   git add .
   git commit -m "Initial commit"
   
   # Create GitHub repo, then:
   git remote add origin https://github.com/YOUR_USERNAME/kaskade.git
   git push -u origin main
   ```

2. **Create gh-pages Branch**
   ```bash
   # Create orphan branch (no history)
   git checkout --orphan gh-pages
   
   # Remove all files from staging
   git rm -rf .
   
   # Copy app files to root
   cp -r app/* .
   
   # Commit
   git add .
   git commit -m "Deploy to GitHub Pages"
   
   # Push
   git push -u origin gh-pages
   ```

3. **Enable GitHub Pages**
   - Go to your GitHub repo
   - Settings → Pages
   - Source: Deploy from branch
   - Branch: `gh-pages` / `root`
   - Save
   - Wait ~2 minutes
   - Your site will be at: `https://YOUR_USERNAME.github.io/kaskade/`

4. **Update Process**
   ```bash
   # Make changes on main branch
   git checkout main
   # ... make changes ...
   git commit -am "Update feature"
   git push origin main
   
   # Deploy to gh-pages
   git checkout gh-pages
   git merge main
   cp -r app/* .
   git add .
   git commit -m "Deploy updates"
   git push origin gh-pages
   ```

### Method B: Using GitHub Actions (Automated)

1. **Create Workflow File**
   
   Create `.github/workflows/deploy.yml`:

   ```yaml
   name: Deploy to GitHub Pages
   
   on:
     push:
       branches: [ main ]
   
   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v3
         
         - name: Deploy to GitHub Pages
           uses: peaceiris/actions-gh-pages@v3
           with:
             github_token: ${{ secrets.GITHUB_TOKEN }}
             publish_dir: ./app
             publish_branch: gh-pages
   ```

2. **Commit and Push**
   ```bash
   git add .github/workflows/deploy.yml
   git commit -m "Add GitHub Actions deployment"
   git push origin main
   ```

3. **Enable GitHub Pages**
   - Go to repo Settings → Pages
   - Source: Deploy from branch
   - Branch: `gh-pages`
   - Every push to `main` now auto-deploys

### Method C: Using npm gh-pages Package

1. **Install Package**
   ```bash
   npm init -y  # If no package.json
   npm install --save-dev gh-pages
   ```

2. **Add Script to package.json**
   ```json
   {
     "scripts": {
       "deploy": "gh-pages -d app"
     }
   }
   ```

3. **Deploy**
   ```bash
   npm run deploy
   ```

---

## Custom Domain Setup

### For Netlify

1. **In Netlify Dashboard**
   - Site settings → Domain management
   - Add custom domain
   - Follow DNS instructions

2. **DNS Configuration** (at your domain registrar)
   ```
   Type: CNAME
   Name: www
   Value: your-site.netlify.app
   
   Type: A
   Name: @
   Value: 75.2.60.5
   ```

### For GitHub Pages

1. **In GitHub Repo**
   - Settings → Pages
   - Custom domain: `yourdomain.com`
   - Save

2. **DNS Configuration**
   ```
   Type: A
   Name: @
   Value: 185.199.108.153
   Value: 185.199.109.153
   Value: 185.199.110.153
   Value: 185.199.111.153
   
   Type: CNAME
   Name: www
   Value: YOUR_USERNAME.github.io
   ```

3. **Add CNAME File**
   
   Create `app/CNAME`:
   ```
   yourdomain.com
   ```

---

## SSL/HTTPS

### Netlify
- Automatic, free SSL via Let's Encrypt
- Enabled by default
- No configuration needed

### GitHub Pages
- Automatic, free SSL
- Enable in Settings → Pages → "Enforce HTTPS"
- May take a few minutes to provision

---

## Environment-Specific Configuration

If you need different behavior in production:

```javascript
// In your JavaScript files
const isProduction = window.location.hostname !== 'localhost';

if (isProduction) {
  // Production-specific code
  console.log = function() {}; // Disable console logs
} else {
  // Development-specific code
  console.log('Running in development');
}
```

---

## Performance Optimization

### Before Deployment

1. **Minify HTML/CSS/JS**
   ```bash
   # Using online tools or:
   npm install -g html-minifier clean-css-cli uglify-js
   
   html-minifier --collapse-whitespace --remove-comments app/index.html -o app/index.min.html
   cleancss app/styles.css -o app/styles.min.css
   uglifyjs app/app.js -o app/app.min.js
   ```

2. **Optimize Images** (if any)
   - Use tools like TinyPNG, ImageOptim
   - Convert to WebP where possible
   - Use appropriate sizes

3. **Check Bundle Size**
   ```bash
   du -sh app/
   # Should be < 1MB for MVP
   ```

### After Deployment

1. **Test Performance**
   - Use Lighthouse in Chrome DevTools
   - Target scores: >90 for Performance, Accessibility, Best Practices

2. **Check Loading**
   - Use Chrome DevTools Network tab
   - Throttle to "Slow 3G"
   - Page should load in <3 seconds

---

## Monitoring & Analytics

### Simple Analytics (Privacy-Friendly)

**Plausible (Recommended)**
```html
<!-- Add to <head> of all pages -->
<script defer data-domain="yourdomain.com" src="https://plausible.io/js/script.js"></script>
```

**Fathom**
```html
<script src="https://cdn.usefathom.com/script.js" data-site="YOUR_SITE_ID" defer></script>
```

### Error Tracking

**Sentry (Optional)**
```html
<script src="https://browser.sentry-cdn.com/7.x.x/bundle.min.js"></script>
<script>
  Sentry.init({
    dsn: 'YOUR_DSN',
    environment: 'production'
  });
</script>
```

---

## Deployment Checklist

Before deploying, verify:

- [ ] All links work (no 404s)
- [ ] No console errors
- [ ] Mobile responsive (test on real device)
- [ ] LocalStorage works
- [ ] All features functional
- [ ] Fast load time (<2s)
- [ ] Lighthouse score >80
- [ ] Tested on multiple browsers
- [ ] README.md included with usage instructions
- [ ] Privacy policy (if collecting any data)

---

## Rollback Procedure

### Netlify
- Go to Deploys tab
- Find previous working deployment
- Click "Publish deploy"

### GitHub Pages
```bash
git checkout gh-pages
git revert HEAD
git push origin gh-pages
```

---

## Continuous Deployment

Once set up with Git-connected deployment:

```bash
# Your workflow becomes:
git add .
git commit -m "Add feature X"
git push origin main

# Netlify/GitHub Pages automatically:
# 1. Detects the push
# 2. Builds the site
# 3. Deploys new version
# 4. Site live in ~1-2 minutes
```

---

## Troubleshooting

### Issue: 404 on deployment
- **Netlify:** Check publish directory is set to `app`
- **GitHub Pages:** Verify gh-pages branch has files in root

### Issue: Broken links
- Use relative paths: `./styles.css` not `/styles.css`
- Or use absolute paths: `/kaskade/styles.css`

### Issue: LocalStorage not working
- Check browser console for security errors
- Verify site is served over HTTPS
- Check browser privacy settings

### Issue: Slow loading
- Check Network tab in DevTools
- Look for large files
- Minify assets
- Enable compression (automatic on Netlify)

---

## Post-Deployment Tasks

1. **Test Deployed Site**
   - Visit URL
   - Test all features
   - Test on mobile device

2. **Share URL**
   - Add to GitHub repo description
   - Share with test users
   - Add to your portfolio/LinkedIn

3. **Monitor**
   - Check analytics after 1 week
   - Look for errors in console
   - Collect user feedback

4. **Update README**
   - Add live URL
   - Add screenshots
   - Add usage instructions

---

## Cost Breakdown

### Netlify (Recommended for MVP)
- **Free tier includes:**
  - 100 GB bandwidth/month
  - Unlimited sites
  - HTTPS
  - Continuous deployment
  - Forms (100 submissions/month)

### GitHub Pages
- **Free tier includes:**
  - 100 GB bandwidth/month
  - 100 GB storage
  - HTTPS
  - Public repos only (or $4/month for private)

**Both are free for your MVP!** 🎉

---

## Next Steps

After successful deployment:

1. **Set up monitoring** (analytics, error tracking)
2. **Collect user feedback** (Google Form, email)
3. **Plan V2 features** based on usage data
4. **Regular updates** (weekly or bi-weekly)
5. **SEO optimization** (meta tags, OpenGraph)

---

## Support Resources

- **Netlify Docs:** https://docs.netlify.com/
- **GitHub Pages Docs:** https://docs.github.com/en/pages
- **Web.dev Performance:** https://web.dev/performance/
- **Lighthouse:** https://developers.google.com/web/tools/lighthouse

---

**You're ready to deploy! Choose your platform and follow the steps above.** 🚀
