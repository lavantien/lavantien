Dotfiles Specialist

```bash
sudo apt update && sudo apt upgrade -y && sudo apt autoremove -y && rustup update && brew upgrade

docker rm $(docker ps -a -q --filter "ancestor=${IMG_ID}")

gh repo list ${REPO_NAME} --limit 1000 | while read -r repo _; do
 gh repo clone "$repo" "$repo" -- -q 2>/dev/null || (
 cd "$repo" || exit
 git checkout -q main 2>/dev/null || true
 git checkout -q master 2>/dev/null || true
 git pull -q
 )
done

:'<,'>norm! @a
```

![](./profile-3d-contrib/profile-night-rainbow.svg)
