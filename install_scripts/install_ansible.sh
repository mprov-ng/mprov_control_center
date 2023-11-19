#!/bin/bash

if [ "$NO_ANSIBLE" ]
then  
  exit 0
fi

dnf -y install ansible-core
