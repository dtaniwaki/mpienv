
function mpienv() {
    command="$1"

    case "$command" in
        "use" )
            {
                eval "$($SHELL ~/.mpienv/mpienv_use.sh $2)"
            }
            ;;
        * )
            echo "Unknown command '$command'"
            ;;
    esac
}
