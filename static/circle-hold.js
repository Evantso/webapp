//track mouse position on mousemove
var mousePosition;
//track state of mousedown and up
var isMouseDown;

//make some circles
var c1 = new Circle(50, 50, 50, "red", "black");
var c2 = new Circle(200, 50, 50, "green", "black");
var c3 = new Circle(350, 50, 50, "blue", "black");
//initialise our circles
var circles = [c1, c2, c3];

//detects whether the mouse cursor is between x and y relative to the radius specified
function intersects(circle) {
    // subtract the x, y coordinates from the mouse position to get coordinates
    // for the hotspot location and check against the area of the radius
    var areaX = mousePosition.x - circle.x;
    var areaY = mousePosition.y - circle.y;
    //return true if x^2 + y^2 <= radius squared.
    return areaX * areaX + areaY * areaY <= circle.r * circle.r;
}

Array.prototype.move = function (old_index, new_index) {
    if (new_index >= this.length) {
        var k = new_index - this.length;
        while ((k--) + 1) {
            this.push(undefined);
        }
    }
    this.splice(new_index, 0, this.splice(old_index, 1)[0]);
};
draw();

 ================================================================
function frame0_loaded(elem) {
    console.log('image loaded. setting up mouse movement');
    $('#frame0').mousemove(function(event){
        var e = jQuery.Event(event);
        console.log("image mousemove x= y=",event.originalEvent.clientX,event.originalEvent.clientY);
        console.log("  e=",e,"client (x,y)=",e.clientX,e.clientY," offset(x,y)=",e.offsetX,e.offsetY);
        // e.offsetX/Y are coordinates within the image
    });
}



    old code:

    const img = new Image();
    img.onload = function() {
        ctx.drawImage(img, 0, 0);

        var centerX = c1.width / 2;
        var centerY = c1.height / 2;
        var radius = 20;

        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI, false);
        ctx.fillStyle = 'red';
        ctx.fill();
        ctx.lineWidth = 5;
        ctx.strokeStyle = '#003300';
        ctx.stroke();
    }
    img.src = url;
    //$('#c1').html(`<img id='frame0' src=${url} onload='frame0_loaded(this)'>`);
