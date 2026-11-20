# Cluster page: landfills with multiple methane plumes

A public page listing every landfill where Carbon Mapper detected 2+ plumes in one satellite pass, month by month. It's updated automatically every morning from Airtable.

## How it works

1. Every day at 10:00 UTC, GitHub Actions runs `scripts/build_clusters.py`.
2. The script reads the **Plume data** table with a read-only Airtable token stored as a GitHub secret, so the token never reaches a browser.
3. It writes only public fields (landfill, state, dates, rates, image and Data Portal links) to `data/clusters.json`. No subscriber data is read.
4. `clusters.html` reads that file and shows the clusters for the chosen month. It defaults to last month, which matches the monthly digest.

**Cluster rules (matching the alerts):** same Scene ID + same Landfill Link, 2 or more plumes. A cluster is listed in the month its **second** plume was published. Clusters are ranked by number of plumes, then by the largest single plume. Rates are never added together.

## Setup (about 20 minutes)

1. **Make a read-only Airtable token.** Go to airtable.com/create/tokens. Scope: `data.records:read` only. Access: the Full Circle Future Matching base only. Use a new token, not the report generator's, so either can be replaced without breaking the other.
2. **Add the files to your `fullcirclefuture` repo** (the one hosting the email icons), keeping the folders:
   - `clusters.html` at the top level
   - `data/clusters.json`
   - `scripts/build_clusters.py`
   - `.github/workflows/cluster-page.yml`

   Tip: folders starting with a dot can get skipped when dragging files in. If `.github` doesn't appear, use **Add file → Create new file**, type `.github/workflows/cluster-page.yml` as the name, and paste the file's contents.
3. **Add the token as a secret.** Repo → Settings → Secrets and variables → Actions → New repository secret. Name: `AIRTABLE_TOKEN`. Value: the token.
4. **Run it once.** Actions tab → "Update cluster page" → Run workflow. The log should say something like `found 42 clusters across 9 months`. If the last step fails with a permissions error, go to Settings → Actions → General → Workflow permissions, choose **Read and write permissions**, and run it again.
5. **Check the page:** https://kimn3fin.github.io/fullcirclefuture/clusters.html

## Putting it on Squarespace

Create a page (for example `/methane-plume-clusters`) and add a **Code** block with:

```html
<div id="clusters-this-month"></div>
<iframe id="fcf-clusters"
  src="https://kimn3fin.github.io/fullcirclefuture/clusters.html?embed=1"
  title="Landfills with multiple methane plumes"
  style="width:100%; border:0; min-height:900px;" loading="lazy"></iframe>
<script>
  window.addEventListener('message', function (e) {
    if (e.origin !== 'https://kimn3fin.github.io') return;
    if (e.data && e.data.type === 'fcf-cluster-height') {
      document.getElementById('fcf-clusters').style.height = e.data.height + 'px';
    }
  });
</script>
```

- `?embed=1` hides the page's own header and footer, since Squarespace provides those.
- The script lets the cluster page tell Squarespace its height, so there's no inner scrollbar or blank gap. Scripts in Code blocks need a Squarespace Business plan or higher.
- The monthly digest can link to `https://www.fullcirclefuture.org/methane-plume-clusters#clusters-this-month`.
- To show a specific month, add it to the address: `clusters.html?embed=1&month=2026-10`.

## Good to know

- **Field names.** The script finds Airtable fields by name. If a field in `REQUIRED` is renamed, the run fails and GitHub emails you. Missing optional fields (like Cluster Map URL) are skipped with a note in the log.
- **Quiet periods.** GitHub pauses scheduled workflows in repos with no commits for 60 days, and the data file only changes when clusters do. GitHub emails a warning first; re-enable it from the Actions tab.
- **Images.** Each cluster shows its Cluster Map URL if there is one, otherwise the largest plume's map, labeled "Largest plume shown."
