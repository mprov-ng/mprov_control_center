#!/bin/bash
. /var/www/mprov_control_center/.env

if [ "$NO_MLX_OFED" == "1" ]
then
  exit 0
fi

role="git+https://github.com/stackhpc/ansible-role-ofed.git"


extravars="ofed_target_release=rhel8.7"

mkdir -p /tmp/mprov/ansible/roles/
ansible-galaxy role install -p /tmp/mprov/ansible/roles/ $role -f
# run the role, hope you set your variables.....
if [[ $role == git* ]]
then
  role=`basename -s .git $role`
fi

cat <<- EOF > /tmp/role.yaml
- hosts: localhost
  become: true
  gather_facts: true
  vars:
    ofed_target_release: rhel8.7
    ofed_nobest: true
  tasks:
    - name: Import role $role
      ansible.builtin.include_role:
        name: $role
EOF
ANSIBLE_ROLES_PATH="/tmp/mprov/ansible/roles" ANSIBLE_GATHER=implicit ansible-playbook -i localhost, -c local -e "${extravars}" /tmp/role.yaml
