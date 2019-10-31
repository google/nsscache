#/usr/bin/env bash

_nsscache ()
{
    local cur prev options commands update_options other_options maps

    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    options='-v --verbose -d --debug -c --config-file --version -h --help'
    commands='update verify status repair help'

    update_options='-f --full --force -m --map -h --help'
    other_options='-m --map -h --help'

    maps="passwd group shadow"

    case "${COMP_CWORD}" in
        1)
            COMPREPLY=( $(compgen -W "${options} ${commands}" -- "${cur}" ))
            ;;
        2)
            case "${prev}" in
                update)
                    COMPREPLY=( $( compgen -W "${update_options}" -- "${cur}" ))
                    return 0
                    ;;
                verify|status|repair)
                    COMPREPLY=( $( compgen -W "${other_options}" -- "${cur}" ))
                    return 0
                    ;;
                -c|--config-file)
                    COMPREPLY=( $( compgen -o plusdirs -f -- "${cur}" ))
                    return 0
                    ;;
                -h|--help|--version|help)
                    return 0
                    ;;
                -v|--verbose|-d|--debug )
                    COMPREPLY=( $( compgen -W "${commands}" -- "${cur}" ))
                    return 0
                    ;;
            esac
            ;;
        3)
            case "${prev}" in
                update)
                    COMPREPLY=( $( compgen -W "${update_options}" -- "${cur}" ))
                    return 0
                    ;;
                verify|status|repair)
                    COMPREPLY=( $( compgen -W "${other_options}" -- "${cur}" ))
                    return 0
                    ;;
                -m|--map)
                    COMPREPLY=( $( compgen -W "${maps}" -- "${cur}" ))
                    return 0
                    ;;
                -f|--full|--force)
                    COMPREPLY=()
                    return 0
                    ;;
                *)
                    COMPREPLY=( $( compgen -W "${commands}" -- "${cur}" ))
                    return 0
                    ;;
            esac
            ;;
        4)
            case "${prev}" in
                update)
                    COMPREPLY=( $( compgen -W "${update_options}" -- "${cur}" ))
                    return 0
                    ;;
                verify|status|repair)
                    COMPREPLY=( $( compgen -W "${other_options}" -- "${cur}" ))
                    return 0
                    ;;
                -m|--map)
                    COMPREPLY=( $( compgen -W "${maps}" -- "${cur}" ))
                    return 0
                    ;;
                -f|--full|--force)
                    COMPREPLY=()
                    return 0
                    ;;
                *)
                    COMPREPLY=( $( compgen -W "${commands}" -- "${cur}" ))
                    return 0
                    ;;
            esac
            ;;
        5)
            case "${prev}" in
                -m|--map)
                    COMPREPLY=( $( compgen -W "${maps}" -- "${cur}" ))
                    return 0
                    ;;
            esac
            ;;
        *)
            COMPREPLY=()
            return 0
            ;;
    esac
}

complete -o filenames -F _nsscache nsscache

# ex: filetype=sh
