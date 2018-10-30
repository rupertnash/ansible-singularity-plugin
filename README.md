# Ansible connection plugin for Singularity

This is based on the ansible-distributed Docker connection plug in

This requires a Singularity *instance* be running.

## Install
Make ansible aware of this plugin. 

1. Install by copying or symlinking it into a directory ansible will search
    * `$PYTHONPATH/lib/python2.7/site-packages/ansible/plugins/connection/`
	* `~/.ansible/plugins/connection`
	* `/usr/share/ansible/plugins/connection`

2. Set the configuration directory to this repo. Either set the `ANSIBLE_CONNECTION_PLUGINS` environment variable or set the `DEFAULT_CONNECTION_PLUGIN_PATH` in your ansible config file like:
```
[defaults]
connection_plugins=path/to/repo
```

See also https://docs.ansible.com/ansible/latest/reference_appendices/config.html

## Enable connection
Then you need to tell ansible to use it! 

1. On the command line with the `-c` option
```
sudo ansible-playbook -c singularity ...
```

2. Via the environment with `ANSIBLE_TRANSPORT` variable
```
export ANSIBLE_TRANSPORT=singularity
sudo ansible....
```

3. Set the ansible configurarion variable `DEFAULT_TRANSPORT` (under section `[defaults]`, set `transport=singularity`).

4. In your inventory set `ansible_connection` to "singularity" for the container

5. In your playbook set the connection option for the play to "singularity"

## Configure inventory

You need to tell ansible which instances to provision. The host name should be the singularity instance name, with it's schema, e.g. `instance://container`. If you put this in a file named e.g. `hosts` then:

```
cat hosts
instance://container ansible_connection=singularity
sudo ansible-playbook -i hosts playbook.yml
```


