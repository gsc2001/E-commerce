import datetime

from django.db.models import Q
from django.core.mail import send_mail, mail_admins
import graphene
from graphene_django import DjangoObjectType
from graphql_jwt.decorators import login_required
import math
import pytz

from .models import *
from .utils import run_async


class CartType(DjangoObjectType):
    class Meta:
        model = CartObj


class ReviewType(DjangoObjectType):
    class Meta:
        model = Review

    likes_count = graphene.Int()
    is_liked = graphene.Boolean()

    def resolve_likes_count(parent, info):
        return Like.objects.filter(review=parent).count()

    @login_required
    def resolve_is_liked(parent, info):
        return Like.objects.filter(review=parent, user=info.context.user).count()


class LikeType(DjangoObjectType):
    class Meta:
        model = Like


class AddressType(DjangoObjectType):
    class Meta:
        model = Address


class AppointmentType(DjangoObjectType):
    class Meta:
        model = Appointment


class ProductType(DjangoObjectType):
    class Meta:
        model = Product


class PhotoType(DjangoObjectType):
    class Meta:
        model = Photo


class ProductOrderInputType(graphene.InputObjectType):
    product_id = graphene.String(required=True)
    qty = graphene.Int(required=True)


class AddressInputType(graphene.InputObjectType):
    name = graphene.String(required=True)
    phone = graphene.String(required=True)
    address1 = graphene.String(required=True)
    address2 = graphene.String(required=True)
    pincode = graphene.Int(required=True)
    city = graphene.String(required=True)
    state = graphene.String(required=True)


class OrderObjType(DjangoObjectType):
    class Meta:
        model = OrderObj
        exclude = ("order",)


class OrderType(DjangoObjectType):
    class Meta:
        model = Order

    product_objects = graphene.List(OrderObjType)

    def resolve_product_objects(parent, info):
        return OrderObj.objects.filter(order=parent)


class UserType(DjangoObjectType):
    class Meta:
        model = User
        exclude = ("password",)  # dont allow password

    cart = graphene.List(CartType)

    def resolve_cart(parent, info):
        return CartObj.objects.filter(user=parent)


class Query(graphene.ObjectType):
    me = graphene.Field(UserType)

    products = graphene.List(
        ProductType,
        first=graphene.Int(),
        skip=graphene.Int(),
        search=graphene.String(),
        kind=graphene.String(),
    )
    product = graphene.Field(ProductType, id=graphene.String())

    orders = graphene.List(OrderType)
    order = graphene.Field(OrderType, id=graphene.String())
    booked_dates = graphene.List(graphene.DateTime)

    @login_required
    def resolve_me(self, info):
        return info.context.user

    @login_required
    def resolve_orders(self, info):
        return Order.objects.filter(user=info.context.user)

    @login_required
    def resolve_order(self, info, id):
        product = Order.objects.get(pk=id)
        if product.user != info.context.user:
            raise Exception("Not the owner of the order")
        return product

    def resolve_booked_dates(self, info):
        appointments = Appointment.objects.filter(
            timestamp__gt=datetime.datetime.now().astimezone()
        )
        booked_dates = [appointment.timestamp for appointment in appointments]
        return booked_dates

    def resolve_product(self, info, id, **kwargs):
        return Product.objects.get(pk=id)

    def resolve_products(
        self, info, first=None, skip=None, search=None, kind=None, **kwargs
    ):
        qs = Product.objects.all()

        if search:
            qs = qs.filter(Q(name__icontains=search))

        if kind:
            qs = qs.filter(Q(kind=kind))

        if skip:
            qs = qs[skip:]

        if first:
            qs = qs[:first]

        return qs


class CreateAddress(graphene.Mutation):
    name = graphene.String()
    phone = graphene.String()
    address1 = graphene.String()
    address2 = graphene.String()
    pincode = graphene.Int()
    city = graphene.String()
    state = graphene.String()
    country = graphene.String()

    class Arguments:
        name = graphene.String()
        phone = graphene.String()
        address1 = graphene.String()
        address2 = graphene.String()
        pincode = graphene.Int()
        city = graphene.String()
        state = graphene.String()
        country = graphene.String()

    @login_required
    def mutate(
        self, info, name, phone, address1, address2, pincode, city, state, country
    ):
        user = info.context.user

        address = Address(
            user=user,
            name=name,
            phone=phone,
            address1=address1,
            address2=address2,
            pincode=pincode,
            city=city,
            state=state,
            country=country,
        )
        address.save()

        return CreateAddress(
            name=address.name,
            phone=address.phone,
            address1=address.address1,
            address2=address.address2,
            pincode=address.pincode,
            city=address.city,
            state=address.state,
            country=address.country,
        )


class DeleteAddress(graphene.Mutation):
    id = graphene.String()

    class Arguments:
        addressId = graphene.String()

    @login_required
    def mutate(self, info, addressId):
        user = info.context.user
        address = Address.objects.get(pk=addressId)

        if address.user.id != user.id:
            raise Exception("You must the owner of that address to remove it!")

        address.delete()

        return DeleteAddress(id=addressId)


class CreateUser(graphene.Mutation):
    id = graphene.String()
    name = graphene.String()
    email = graphene.String()
    phone = graphene.String()

    class Arguments:
        name = graphene.String()
        email = graphene.String()
        phone = graphene.String()
        password = graphene.String()

    def mutate(self, info, name, email, phone, password):
        user = User(name=name, email=email, phone=phone)
        user.set_password(password)
        user.save()

        return CreateUser(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
        )


class AddReview(graphene.Mutation):
    id = graphene.String()
    rating = graphene.Int()
    text = graphene.String()

    class Arguments:
        rating = graphene.Int()
        text = graphene.String()
        productId = graphene.String()

    @login_required
    def mutate(self, info, rating, productId, **kwargs):
        text = kwargs.get("text", None)
        user = info.context.user
        review = Review(user=user, product_id=productId, rating=rating, text=text)
        review.save()

        return AddReview(id=review.id, rating=review.rating, text=review.text)


class DeleteReview(graphene.Mutation):
    id = graphene.String()

    class Arguments:
        reviewId = graphene.String()

    @login_required
    def mutate(self, info, reviewId):
        user = info.context.user
        review = Review.objects.get(pk=reviewId)

        if review.user.id != user.id:
            raise Exception("You must be author of the review to delete it.")

        review.delete()

        return DeleteReview(id=reviewId)


class LikeReview(graphene.Mutation):
    id = graphene.String()

    class Arguments:
        reviewId = graphene.String()

    @login_required
    def mutate(self, info, reviewId):
        user = info.context.user
        like = Like(user=user, review_id=reviewId)
        like.save()

        return LikeReview(id=like.id)


class UnlikeReview(graphene.Mutation):
    id = graphene.String()

    class Arguments:
        reviewId = graphene.String()

    @login_required
    def mutate(self, info, reviewId):
        user = info.context.user
        like = Like.objects.get(user=user, review_id=reviewId)
        id = like.id
        like.delete()

        return UnlikeReview(id=id)


class UpdateSelf(graphene.Mutation):
    user = graphene.Field(UserType)

    class Arguments:
        phone = graphene.String()
        name = graphene.String()
        address = AddressInputType()

    @login_required
    def mutate(self, info, **kwargs):
        user = info.context.user
        if "phone" in kwargs.keys():
            user.phone = kwargs.get("phone")
        if "name" in kwargs.keys():
            user.name = kwargs.get("name")
        # for single address
        if "address" in kwargs.keys():
            address = ""
            try:
                address = Address.objects.get(user=user)
            except Address.DoesNotExist:
                address = Address(user=user)
            address.name = kwargs.get("address").name
            address.phone = kwargs.get("address").phone
            address.address1 = kwargs.get("address").address1
            address.address2 = kwargs.get("address").address2
            address.pincode = kwargs.get("address").pincode
            address.city = kwargs.get("address").city
            address.state = kwargs.get("address").state
            address.save()
        user.save()
        return UpdateSelf(user=user)


class UpdatePassword(graphene.Mutation):
    user = graphene.Field(UserType)

    class Arguments:
        old_pass = graphene.String()
        new_pass = graphene.String()

    @login_required
    def mutate(self, info, old_pass, new_pass):
        user = info.context.user

        if not user.check_password(old_pass):
            raise Exception("Old password not correct")
        else:
            user.set_password(new_pass)
            user.save()
            return UpdatePassword(user=user)


class OrderCart(graphene.Mutation):
    order = graphene.Field(OrderType)

    class Arguments:
        address_id = graphene.String()

    @login_required
    def mutate(self, info, address_id):
        address = Address.objects.get(pk=address_id)
        user = info.context.user
        order = Order.objects.create(
            user=user,
            name=address.name,
            phone=address.phone,
            address1=address.address1,
            address2=address.address2,
            pincode=address.pincode,
            city=address.city,
            state=address.state,
            country=address.country,
        )
        cart = CartObj.objects.filter(user=info.context.user)

        for cart_obj in cart:
            product = cart_obj.product

            if product.stock < cart_obj.qty:
                raise Exception("Stock Error")

            product.stock -= cart_obj.qty
            product.save()

            order.product_objects.add(
                product.id,
                through_defaults={
                    "qty": cart_obj.qty,
                    "price": math.ceil(
                        product.price - (product.discount * product.price) / 100
                    ),
                },
            )

            cart_obj.delete()

        run_async(
            send_mail,
            [
                f"Order Confirmed Id: {order.id}",
                f"Dear {user.name},\n\n Your order is confirmed with order id: {order.id}. Please go to your orders section in app to see the order details",
                "Larena Team",
                [user.email],
            ],
        )

        run_async(
            mail_admins,
            [
                f"Order Confirmed Id: {order.id}",
                f"A order has been placed with order id : {order.id}",
            ],
        )

        return OrderCart(order=order)


class OrderProduct(graphene.Mutation):
    order = graphene.Field(OrderType)

    class Arguments:
        product_obj = ProductOrderInputType()
        address_id = graphene.String()

    @login_required
    def mutate(self, info, product_obj, address_id):
        address = Address.objects.get(pk=address_id)
        user = info.context.user
        order = Order.objects.create(
            user=user,
            name=address.name,
            phone=address.phone,
            address1=address.address1,
            address2=address.address2,
            pincode=address.pincode,
            city=address.city,
            state=address.state,
            country=address.country,
        )

        product = Product.objects.get(pk=product_obj.product_id)
        if product.stock < product_obj.qty:
            raise Exception("Stock Error")

        product.stock -= product_obj.qty
        product.save()

        order.product_objects.add(
            product.id,
            through_defaults={
                "qty": product_obj.qty,
                "price": math.ceil(
                    product.price - (product.discount * product.price) / 100
                ),
            },
        )

        run_async(
            send_mail,
            [
                f"Order Confirmed Id: {order.id}",
                f"Dear {user.name},\n\n Your order is confirmed with order id: {order.id}. Please go to your orders section in app to see the order details",
                "Larena Team",
                [user.email],
            ],
        )

        run_async(
            mail_admins,
            [
                f"Order Confirmed Id: {order.id}",
                f"A order has been placed with order id : {order.id}",
            ],
        )

        return OrderProduct(order=order)


class SetCart(graphene.Mutation):
    cart = graphene.List(CartType)

    class Arguments:
        cart_obj = ProductOrderInputType()
        add = graphene.Boolean()

    @login_required
    def mutate(self, info, cart_obj, **kwargs):
        user = info.context.user
        add = kwargs.get("add", False)
        try:
            _cart_obj = CartObj.objects.get(user=user, product_id=cart_obj.product_id)
            if add:
                _cart_obj.qty += cart_obj.qty
                _cart_obj.save()
            else:
                if cart_obj.qty > 0:
                    _cart_obj.qty = cart_obj.qty
                    _cart_obj.save()
                else:
                    user.cart.remove(cart_obj.product_id)
        except CartObj.DoesNotExist:
            if cart_obj.qty > 0:
                user.cart.add(cart_obj.product_id, through_defaults={"qty": cart_obj.qty})

        return SetCart(cart=CartObj.objects.filter(user=user))


class BookAppointment(graphene.Mutation):
    appointment = graphene.Field(AppointmentType)

    class Arguments:
        timestamp = graphene.DateTime()

    @login_required
    def mutate(self, info, timestamp):
        _appoint = Appointment.objects.filter(timestamp__startswith=timestamp.date())

        if len(_appoint) > 0:
            raise Exception("No slot on that day!")
        user = info.context.user
        new_appoint = Appointment.objects.create(user=user, timestamp=timestamp)

        _time: datetime.datetime = new_appoint.timestamp.astimezone(
            pytz.timezone("Asia/Kolkata")
        )

        formatted_time = _time.strftime("%-I:%M on %A, %-d{} %B")
        if _time.day == 1:
            formatted_time = formatted_time.format("st")
        elif _time.day == 2:
            formatted_time = formatted_time.format("nd")
        elif _time.day == 3:
            formatted_time = formatted_time.format("rd")
        else:
            formatted_time = formatted_time.format("th")
        run_async(
            send_mail,
            [
                "Appointment Confirmed",
                f"Dear {user.name},\n\tThank you for booking appointment.\n\tYour appointment is at {formatted_time}.\n\nThanks,\n Larena team",
                "Larena Team",
                [user.email],
            ],
        )

        run_async(
            mail_admins,
            [
                "Appointment Confirmed",
                f"New appoitment booked by {user.name} Phn: {user.phone} at {formatted_time}",
            ],
        )

        return BookAppointment(appointment=new_appoint)


class Mutation(graphene.ObjectType):
    create_user = CreateUser.Field()
    create_address = CreateAddress.Field()
    delete_address = DeleteAddress.Field()
    add_review = AddReview.Field()
    delete_review = DeleteReview.Field()
    like_review = LikeReview.Field()
    unlike_review = UnlikeReview.Field()
    update_me = UpdateSelf.Field()
    update_password = UpdatePassword.Field()
    order_cart = OrderCart.Field()
    set_cart = SetCart.Field()
    book_appointment = BookAppointment.Field()
    order_product = OrderProduct.Field()
