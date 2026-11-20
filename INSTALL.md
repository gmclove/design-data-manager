# Installing the Design Data Manager and Its Revit Add-in

This guide walks you through setting up the Design Data Manager on your computer and adding its
**Design Data** tab to Revit. You don't need any technical background. Follow the steps in order.

It takes about 10 minutes.

---

## What You Need

- A Windows computer.
- **Revit 2025** installed. Any Revit 2025 update works.
- An internet connection, to download the program and its updates.

You **don't** need administrator rights, and you don't need to install anything else.

---

## Part 1: Download the Program and Put It in a Permanent Folder

The Design Data Manager is a single program file. It doesn't have an installer; you just keep it
in a folder and open it from there.

**Download it:**

1. Open this page in your web browser (Edge or Chrome):
   **https://github.com/gmclove/design-data-manager/releases/latest**
   - You don't need a GitHub account.
2. Scroll down to the section called **Assets**. Click **DesignDataManager.exe** in that list.
   - Don't click "Source code (zip)" or "Source code (tar.gz)". Those are for developers.
3. Your browser downloads the file into your **Downloads** folder.
   - **Edge** may say the file "isn't commonly downloaded". Hover over the message, click the
     **...** (three dots), choose **Keep**, then **Show more**, then **Keep anyway**.
   - **Chrome** may ask whether to keep the file. Choose **Keep**.

**Put it in a permanent folder:**

1. Open **File Explorer**: press the **Windows key + E** together.
2. In the left-hand list, click **Documents**.
3. Make a new folder for the program:
   1. Right-click an empty white area in the Documents window.
   2. Choose **New**, then **Folder**.
   3. Type the name **Design Data Manager** and press **Enter**.
4. Move **DesignDataManager.exe** into that new folder:
   1. In the left-hand list, click **Downloads**.
   2. Right-click **DesignDataManager.exe** and choose **Cut**. On Windows 11 it's the scissors
      icon at the top of the menu.
   3. Go back to **Documents > Design Data Manager**.
   4. Right-click an empty white area and choose **Paste**.

> **Why a permanent folder?** Revit remembers where the program is, so its **Design Data
> Manager** button can open it. If you leave the file in **Downloads** and later clean that folder
> out, the button stops working. If you do move the file, just open it once from its new place
> and Revit will find it again.

**Optional: a desktop shortcut.** Right-click **DesignDataManager.exe**, choose **Show more
options** (Windows 11 only), then **Send to > Desktop (create shortcut)**.

---

## Part 2: Open the Program for the First Time

1. Double-click **DesignDataManager.exe**.
2. **Windows may show a blue box that says "Windows protected your PC".** This happens because
   the program was made in-house and isn't registered with Microsoft. It's safe to run.
   1. Click **More info** (small underlined text under the message).
   2. Click the **Run anyway** button that appears.

   You only have to do this the first time.
3. **Wait.** The program takes **about 10 seconds** to open, sometimes longer the first time. Nothing
   may seem to happen for a while. **Don't double-click it again**, or you'll end up with two copies
   open.
4. A window titled **DDM Review** opens, showing tabs such as **Parameters** and **Families**.
   The program is working.

The program keeps its data in a **data** folder that it creates next to
**DesignDataManager.exe**. Don't delete that folder.

---

## Part 3: Add the Design Data Tab to Revit

1. **Close Revit completely**, including every Revit window. Save your work first.
2. In the **DDM Review** window, find the row of buttons near the top and click
   **Install Revit Add-in...**.
3. A message appears.
   - **"Revit 2025: installed..."** means it worked. Click **OK** and go to Part 4.
   - **Any other message:** see [Troubleshooting](#troubleshooting) below.

---

## Part 4: Start Revit and Allow the Add-in

1. Start **Revit 2025** as you normally do.
2. **The first time, Revit shows a box titled "Security - Unsigned Add-In"** asking about
   **Design Data Manager**. Revit asks this about any add-in made in-house.

   Click **Always Load**. If you click **Load Once**, Revit will ask again every time it starts.
   If you click **Do Not Load**, see [Troubleshooting](#troubleshooting).
3. Open any project.
4. At the top of Revit, next to tabs such as **Architecture**, **Systems** and **Annotate**, there
   is now a tab called **Design Data**. Click it. You should see:

   | Group | Buttons |
   |---|---|
   | **Schedules** | **Build Schedules**, **Design Data Manager** |
   | **Linker** | **Assign IDs**, **Link Elements**, **Sync Linked Elements** |

   Each button has a small blue picture. Hold the mouse over a button to see what it does.

You're done with the install. Next, connect to the team's database.

---

## Part 5: Connect to the Team Database

Right after installing, the program uses its **own starter copy** of the database. To work with the
team's database instead, point it at the shared folder once. After that, the program and the Revit
add-in always use the team database.

**Step 1: Get the shared folder onto your computer.** The team database lives in a OneDrive folder
called **ddm-data**, which your BIM lead shares with you.

1. Open the link to **ddm-data** that your BIM lead sent you. It opens in your web browser.
2. Near the top of the page, click **Add shortcut to My files**.
   - If you don't see it, click the **...** (three dots) first.
3. Wait a minute for OneDrive to sync it. Then open **File Explorer** (Windows key + E). In the left-hand
   list, click **OneDrive - IPS**. The **ddm-data** folder is now there.
4. Right-click **ddm-data** and choose **Always keep on this device**. This keeps the database on
   your computer, not just online, so the program and Revit can always read it.

**Step 2: Point the program at it.**

1. Open the Design Data Manager.
2. At the bottom left of the **DDM Review** window, click **Database Location...**.
3. A folder picker opens. Go to **OneDrive - IPS**, then click the **ddm-data** folder once to
   highlight it.
4. Click **Select Folder**.
   - If you made changes in the starter copy, the program first asks whether to save them. Choose
     **Discard**; you're switching to the team database.
5. The program opens the team database. Next to the **Database Location...** button it now says
   **Database:** followed by a path ending in `ddm-data\database.ddm.json`.

That's it. From now on the program opens the team database by itself, and the **Design Data** tab in
Revit uses it too.

> **If it asks "There's no database in ... yet. Save the open database there?"**, click **No**.
> You picked the wrong folder. The team folder already has a database in it. Try again and pick
> **ddm-data** itself, not a folder inside it or above it.

### Editing the Team Database: One Person at a Time

Everyone opens the same database file. **Only one person may make and save changes at a time.**
If two people save, the last save replaces the other person's work.

- **Before you change anything,** check with your BIM lead that nobody else is editing.
- **Make sure OneDrive is up to date first.** The OneDrive cloud icon at the bottom right of the
  screen should show no syncing arrows. Close and reopen the program so it reads the latest copy.
- **Save when you're done,** and wait for OneDrive to finish syncing before you tell others you're
  finished.
- **Just looking or using Revit?** Open the program as usual, but don't click **Save**.

---

## Getting Updates

The program checks for a new version **by itself, every time you open it**. You don't need to
download anything again.

**When there's a new version:**

1. A few seconds after the program opens, a box titled **Update Available** appears. It says which
   version is available and lists what's new.
2. **Close Revit first.** The update also updates the Design Data tab in Revit, and it can't do
   that while Revit is open.
3. Click **Yes**.
   - If you have unsaved changes, the program asks whether to save them first. Choose **Save**.
   - Click **No** if now isn't a good time. It asks again the next time you open the program.
4. Wait while it downloads. This takes under a minute on a normal connection. The program then
   closes and opens again by itself, now on the new version. The version number is in the window's
   title bar, for example **DDM Review 0.2.0 Beta**.
5. Start Revit as usual. The Design Data tab is now up to date too.

**To check by hand at any time:** click **Check for Updates...** near the top right of the
**DDM Review** window.
- "You have the latest version" means there's nothing to do.
- Otherwise, follow steps 2 to 5 above.

**If Revit was open during the update,** a box titled **Update the Revit Add-in** appears after the
restart. Close Revit, then click **Install Revit Add-in...**. If it still says Revit is using the
add-in, see the first item under [Troubleshooting](#troubleshooting).

**If the update can't download** (no internet, or a company firewall), you'll see a message saying
so, and your current version keeps working. You can also update by hand: download
**DesignDataManager.exe** again as in Part 1 and put it in **Documents > Design Data Manager** on top
of the old one, choosing **Replace the file in the destination**. Then open it and click **Install
Revit Add-in...** with Revit closed.

---

## Troubleshooting

### "Revit 2025 is using the add-in, so it can't be replaced", but I closed Revit

Revit sometimes keeps running in the background after you close its window, for example while it
finishes syncing a cloud model. While it runs, it keeps the add-in in use.

1. Press **Ctrl + Shift + Esc** together. **Task Manager** opens.
   - If you see only a small window with a short list, click **More details** at the bottom.
2. Click the **Processes** tab if it isn't already selected.
3. Look for any entry named **Revit** or **Autodesk Revit 2025**.
   - Use the search box at the top, or click the **Name** heading to sort the list
     alphabetically.
4. Click the Revit entry once, then click **End task**. There's a button at the top right, or you
   can right-click the entry and choose **End task**. Do this for **every** Revit entry.
   - These sessions have no window, so there's nothing in them you can still save.
5. Close Task Manager.
6. Go back to the **DDM Review** window and click **Install Revit Add-in...** again.

**Still not working?** Restart your computer. Then, **before opening Revit**, open the Design Data
Manager and click **Install Revit Add-in...**.

### "No Revit 2025 or later is installed"

The program looked for Revit 2025 in the usual place, `C:\Program Files\Autodesk\Revit 2025`, and
didn't find it. Check that Revit 2025 is installed on this computer. If it is installed somewhere
unusual, ask your BIM lead.

### "This copy of the Design Data Manager has no add-in built for it"

You have a Revit version, such as Revit 2026, that this copy of the program doesn't support yet.
The add-in is still installed for Revit 2025 if you have it. Ask your BIM lead about other Revit
versions.

### There's no Design Data tab in Revit

- **Check that Part 3 said "installed"**, and that Revit was fully closed when you clicked the
  button. Then start Revit again.
- **You clicked "Do Not Load" on the security box.** Revit remembers that choice, so you need to
  undo it:
  1. Close Revit.
  2. Press **Windows key + R**. A small **Run** box opens.
  3. Paste in `%APPDATA%\Autodesk\Revit\Addins\2025` and press **Enter**. A folder opens.
  4. Delete the file **DesignDataManager.addin** and the folder **DesignDataManager**.
  5. Go back to Part 3 and install again. This time choose **Always Load** in Revit.
- **Still missing?** In Revit, look on the **Add-Ins** tab for a message about Design Data
  Manager, or ask your BIM lead.

### The buttons on the Design Data tab have no pictures

You have an old version of the add-in. Close Revit, open the Design Data Manager, click **Check
for Updates...** and follow [Getting Updates](#getting-updates). If you're already on the latest
version, just click **Install Revit Add-in...** with Revit closed.

### The program or Revit shows old data, or not the team's

- **Check the Database line** at the bottom of the **DDM Review** window. It should end in
  `ddm-data\database.ddm.json`. If it doesn't, follow [Part 5](#part-5-connect-to-the-team-database)
  again.
- **Check OneDrive has finished syncing:** no arrows on the cloud icon at the bottom right of the
  screen. Then close and reopen the program.
- **Revit uses the database as of its last Save.** If someone just saved, the schedules in Revit
  update the next time you click **Build Schedules**, or when Revit offers to apply the changes.

### The Design Data Manager button in Revit doesn't open the program

Revit opens the program from the place where it was last opened. If you moved or renamed
**DesignDataManager.exe**, double-click it once from its new place, then try the button again.

### Windows says the file "can't be opened" or deletes it

Some company security software blocks new programs. Ask IT to allow **DesignDataManager.exe**,
and mention that your BIM lead provided it. Its download page is
https://github.com/gmclove/design-data-manager/releases.

---

## Removing the Add-in

1. Close Revit.
2. Press **Windows key + R**, paste `%APPDATA%\Autodesk\Revit\Addins\2025` and press **Enter**.
3. Delete the file **DesignDataManager.addin** and the folder **DesignDataManager**.

To remove the program too, delete the **Documents > Design Data Manager** folder. This also deletes
your data, so keep a copy of its **data** folder if you need it.

---

## Getting Help

In the **DDM Review** window, click **Create GitHub Ticket** (top right) to report a problem, or
contact your BIM lead.
