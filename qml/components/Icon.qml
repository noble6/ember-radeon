import QtQuick
import QtQuick.Shapes

Item {
    id: root
    property string name: "home"
    property color color: Theme.ink
    property real size: 24
    implicitWidth: size
    implicitHeight: size
    Shape {
        width: 24; height: 24
        scale: root.size / 24
        transformOrigin: Item.TopLeft
        preferredRendererType: Shape.GeometryRenderer
        ShapePath {
            strokeWidth: -1
            fillColor: root.color
            PathSvg { path: Icons.paths[root.name] || Icons.paths["home"] }
        }
    }
}
