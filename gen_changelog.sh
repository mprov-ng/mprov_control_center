#!/usr/bin/env bash
prev_tag=$1
cur_tag=$2
previous_tag=${prev_tag:="0"}

current_tag=${cur_tag:="HEAD"}

if [ "$previous_tag" != 0 ];then
    tag_date=$(git log -1 --pretty=format:'%ad' --date=short ${previous_tag})
    printf "## Changes since ${previous_tag} (${tag_date})\n\n"
    git log ${current_tag}...${previous_tag} --pretty=format:'*  %s [View](https://github.com/mprov-ng/mprov_control_center/commit/%H)' --reverse | grep -v Merge
    printf "\n\n"
else
    # no previous tag: everything up to current_tag, headed with it
    tag_date=$(git log -1 --pretty=format:'%ad' --date=short ${current_tag})
    printf "## ${current_tag} (${tag_date})\n\n"
    git log ${current_tag} --pretty=format:'*  %s [View](https://github.com/mprov-ng/mprov_control_center/commit/%H)' --reverse | grep -v Merge
fi
previous_tag=${current_tag}
